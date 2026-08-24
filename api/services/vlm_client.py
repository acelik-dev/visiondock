"""Shared Azure OpenAI client with optional Langfuse tracing."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

VLM_ENDPOINT = os.getenv("VLM_ENDPOINT", "https://vision-doc-ai.openai.azure.com/openai/v1")
VLM_API_KEY = os.getenv("VLM_API_KEY", "")
VLM_MODEL = os.getenv("VLM_MODEL", "gpt-4.1-mini")

_client: Any = None
_langfuse_ready = False


def langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY"))


def _langfuse_host() -> str:
    """Langfuse Python v2 reads LANGFUSE_HOST; we also accept LANGFUSE_BASE_URL."""
    return (
        (os.getenv("LANGFUSE_HOST") or "").strip()
        or (os.getenv("LANGFUSE_BASE_URL") or "").strip()
        or "https://cloud.langfuse.com"
    )


def _configure_langfuse_env() -> None:
    """Prefer immediate export so traces don't sit in the worker buffer."""
    # Langfuse v2 defaults flush_at=15 — with gunicorn that often only ships on
    # process shutdown (redeploy). Force flush after every event.
    os.environ["LANGFUSE_FLUSH_AT"] = os.getenv("LANGFUSE_FLUSH_AT") or "1"
    os.environ["LANGFUSE_FLUSH_INTERVAL"] = os.getenv("LANGFUSE_FLUSH_INTERVAL") or "0.5"
    # SDK v2 ignores LANGFUSE_BASE_URL; mirror it onto LANGFUSE_HOST.
    host = _langfuse_host()
    os.environ["LANGFUSE_HOST"] = host
    if not (os.getenv("LANGFUSE_BASE_URL") or "").strip():
        os.environ["LANGFUSE_BASE_URL"] = host


def ensure_langfuse_client() -> Any | None:
    """
    Seed LangfuseSingleton with flush_at=1 *before* the OpenAI wrapper creates it.

    The openai integration calls LangfuseSingleton().get() without flush_at; the first
    get() wins, so we must initialize first or events buffer until process death.
    """
    global _langfuse_ready
    if not langfuse_enabled():
        return None

    _configure_langfuse_env()
    try:
        from langfuse.utils.langfuse_singleton import LangfuseSingleton

        client = LangfuseSingleton().get(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=_langfuse_host(),
            flush_at=int(os.environ.get("LANGFUSE_FLUSH_AT", "1")),
            flush_interval=float(os.environ.get("LANGFUSE_FLUSH_INTERVAL", "0.5")),
            sdk_integration="openai",
        )
        if not _langfuse_ready:
            logger.info(
                "Langfuse client ready (host=%s flush_at=%s flush_interval=%s)",
                _langfuse_host(),
                os.environ.get("LANGFUSE_FLUSH_AT"),
                os.environ.get("LANGFUSE_FLUSH_INTERVAL"),
            )
            _langfuse_ready = True
        return client
    except Exception as exc:
        logger.warning("Langfuse client init failed: %s", exc)
        return None


def _openai_client_class():
    if langfuse_enabled():
        ensure_langfuse_client()
        from langfuse.openai import OpenAI as LangfuseOpenAI

        logger.info("Langfuse tracing enabled for VLM calls")
        return LangfuseOpenAI
    from openai import OpenAI

    return OpenAI


def get_vlm_client() -> Any | None:
    global _client
    if not VLM_API_KEY:
        return None
    if _client is None:
        OpenAI = _openai_client_class()
        _client = OpenAI(base_url=VLM_ENDPOINT, api_key=VLM_API_KEY)
        logger.info("VLM client ready (endpoint=%s model=%s)", VLM_ENDPOINT, VLM_MODEL)
    return _client


def vlm_model() -> str:
    return VLM_MODEL


def _is_reasoning_model() -> bool:
    return (VLM_MODEL or "").lower().startswith(("gpt-5", "o1", "o3", "o4"))


def vlm_token_kwargs(limit: int) -> dict[str, int]:
    if _is_reasoning_model():
        return {"max_completion_tokens": limit}
    return {"max_tokens": limit}


def vlm_json_kwargs(limit: int) -> dict[str, Any]:
    """Budget for structured-JSON calls.

    Reasoning models spend the completion budget thinking and then return an empty
    message with finish_reason=length, so keep the effort minimal and the cap high.
    """
    kwargs: dict[str, Any] = dict(vlm_token_kwargs(limit))
    model = (VLM_MODEL or "").lower()
    if model.startswith("gpt-5"):
        kwargs["reasoning_effort"] = "minimal"
    elif model.startswith(("o1", "o3", "o4")):
        kwargs["reasoning_effort"] = "low"
    return kwargs


def vlm_trace_kwargs(
    *,
    name: str,
    project_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extra kwargs for chat.completions.create when Langfuse is configured."""
    if not langfuse_enabled():
        return {}
    meta: dict[str, Any] = dict(metadata or {})
    if project_id:
        meta.setdefault("project_id", project_id)
    kw: dict[str, Any] = {"name": name}
    if meta:
        kw["metadata"] = meta
    if project_id:
        kw["session_id"] = project_id
    if user_id:
        kw["user_id"] = str(user_id)
    if tags:
        kw["tags"] = tags
    return kw


def trace_user_id(request: Any) -> str | None:
    try:
        uid = request.session.get("user_id")
    except Exception:
        return None
    return str(uid) if uid is not None else None


def flush_langfuse() -> None:
    """Force-send buffered Langfuse events (Langfuse Python v2 OpenAI wrapper)."""
    if not langfuse_enabled():
        return

    paths_ok: list[str] = []
    paths_failed: list[str] = []

    # 1) Explicit singleton (primary — same client the OpenAI wrapper uses)
    try:
        client = ensure_langfuse_client()
        if client is not None:
            client.flush()
            paths_ok.append("singleton")
        else:
            paths_failed.append("singleton:no-client")
    except Exception as exc:
        paths_failed.append(f"singleton:{exc}")
        logger.warning("Langfuse singleton flush failed: %s", exc)

    # 2) Official path for langfuse.openai drop-in (v2): openai.flush_langfuse()
    #    Guard: OpenAILangfuse.flush() does `self._langfuse.flush()` with no None check.
    try:
        import openai

        flush_fn = getattr(openai, "flush_langfuse", None)
        if callable(flush_fn):
            bound_self = getattr(flush_fn, "__self__", None)
            if bound_self is not None and getattr(bound_self, "_langfuse", None) is None:
                paths_failed.append("openai.flush_langfuse:not-initialized")
            else:
                flush_fn()
                paths_ok.append("openai.flush_langfuse")
    except Exception as exc:
        paths_failed.append(f"openai.flush_langfuse:{exc}")
        logger.warning("Langfuse openai.flush_langfuse failed: %s", exc)

    # 3) Langfuse v3-style get_client (future-proof)
    if not paths_ok:
        try:
            from langfuse import get_client  # type: ignore

            get_client().flush()
            paths_ok.append("get_client")
        except Exception as exc:
            paths_failed.append(f"get_client:{exc}")

    if paths_ok:
        logger.info("Langfuse flush completed via %s", ",".join(paths_ok))
    else:
        logger.warning(
            "Langfuse flush could not find an active client (%s)",
            "; ".join(paths_failed) or "no paths tried",
        )
