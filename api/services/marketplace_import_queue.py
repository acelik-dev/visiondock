"""Background marketplace dataset imports (avoids HTTP 504 on large zip extraction)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_results: dict[str, dict[str, Any]] = {}
_errors: dict[str, str] = {}
_inflight: set[str] = set()


def import_job_id(project_id: str) -> str:
    return f"mp-import-{project_id}"


def is_inflight(project_id: str) -> bool:
    with _lock:
        return import_job_id(project_id) in _inflight


def peek_import_result(project_id: str) -> dict[str, Any] | None:
    with _lock:
        return _results.get(import_job_id(project_id))


def peek_import_error(project_id: str) -> str | None:
    with _lock:
        return _errors.get(import_job_id(project_id))


def reserve_import(project_id: str) -> bool:
    """Mark import as in-flight before HTTP returns. Returns False if already reserved."""
    job_id = import_job_id(project_id)
    with _lock:
        if job_id in _inflight:
            return False
        _inflight.add(job_id)
        _errors.pop(job_id, None)
        _results.pop(job_id, None)
        return True


def start_import(project_id: str, import_fn: Callable[[], dict[str, Any]]) -> None:
    job_id = import_job_id(project_id)
    with _lock:
        if job_id not in _inflight:
            _inflight.add(job_id)
        _errors.pop(job_id, None)
        _results.pop(job_id, None)

    def _run() -> None:
        try:
            result = import_fn()
            with _lock:
                _results[job_id] = result
        except Exception as e:
            logger.exception("Background marketplace import failed for %s", project_id)
            with _lock:
                _errors[job_id] = str(e).strip() or "Marketplace import failed"
        finally:
            with _lock:
                _inflight.discard(job_id)

    threading.Thread(target=_run, name=job_id, daemon=True).start()
