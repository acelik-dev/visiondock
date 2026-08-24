"""In-memory background Azure ML job submission (avoids HTTP 504 on long uploads)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_results: dict[str, dict[str, Any]] = {}
_errors: dict[str, str] = {}
_inflight: set[str] = set()


def is_inflight(job_id: str) -> bool:
    with _lock:
        return job_id in _inflight


def peek_submission_result(job_id: str) -> dict[str, Any] | None:
    with _lock:
        return _results.get(job_id)


def clear_submission_result(job_id: str) -> None:
    with _lock:
        _results.pop(job_id, None)


def get_submission_error(job_id: str) -> str | None:
    with _lock:
        return _errors.pop(job_id, None)


def peek_error(job_id: str) -> str | None:
    with _lock:
        return _errors.get(job_id)


def start_submission(job_id: str, submit_fn: Callable[[], dict[str, Any]]) -> None:
    with _lock:
        if job_id in _inflight:
            raise ValueError(f"Submission already in progress for {job_id}")
        _inflight.add(job_id)
        _errors.pop(job_id, None)
        _results.pop(job_id, None)

    def _run() -> None:
        try:
            result = submit_fn()
            with _lock:
                _results[job_id] = result
        except Exception as e:
            logger.exception("Background training submit failed for %s", job_id)
            with _lock:
                _errors[job_id] = str(e).strip() or "Training submission failed"
        finally:
            with _lock:
                _inflight.discard(job_id)

    threading.Thread(target=_run, name=f"aml-submit-{job_id}", daemon=True).start()
