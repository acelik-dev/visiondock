"""Persisted admin overrides for plans and action credit costs."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from storage.blob_store import get_blob_store

CONFIG_KEY = "admin/billing_config.json"

_DEFAULT_ACTION_KEYS = (
    "vlm_analyze",
    "generate_config",
    "pipeline_tune",
    "training_submit",
    "inference_deploy",
    "inference_predict",
)

_cache: dict[str, Any] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_config() -> dict[str, Any]:
    from services.credits import PLANS
    from services.azure_pricing import CREDIT_USD, PLATFORM_MARKUP, action_credits

    action_credits_map: dict[str, int] = {}
    for key in _DEFAULT_ACTION_KEYS:
        try:
            action_credits_map[key] = int(action_credits(key))
        except Exception:
            action_credits_map[key] = 1

    return {
        "version": "1",
        "updated_at": None,
        "credit_usd": float(CREDIT_USD),
        "platform_markup": float(PLATFORM_MARKUP),
        "action_credits": action_credits_map,
        "plans": deepcopy(PLANS),
    }


def get_billing_config(*, refresh: bool = False) -> dict[str, Any]:
    global _cache
    if _cache is not None and not refresh:
        return deepcopy(_cache)

    store = get_blob_store()
    raw = store.read_json(CONFIG_KEY)
    base = _default_config()
    if isinstance(raw, dict):
        if isinstance(raw.get("action_credits"), dict):
            for k, v in raw["action_credits"].items():
                try:
                    base["action_credits"][str(k)] = max(0, int(v))
                except (TypeError, ValueError):
                    continue
        if isinstance(raw.get("plans"), dict):
            for pid, plan in raw["plans"].items():
                if not isinstance(plan, dict):
                    continue
                cur = base["plans"].setdefault(str(pid), {"id": str(pid)})
                for field in ("name", "description"):
                    if field in plan and plan[field] is not None:
                        cur[field] = str(plan[field])
                if "credits" in plan:
                    try:
                        cur["credits"] = max(0, int(plan["credits"]))
                    except (TypeError, ValueError):
                        pass
                if "price_usd" in plan:
                    try:
                        cur["price_usd"] = None if plan["price_usd"] is None else float(plan["price_usd"])
                    except (TypeError, ValueError):
                        pass
                cur["id"] = str(pid)
        if raw.get("credit_usd") is not None:
            try:
                base["credit_usd"] = max(0.0001, float(raw["credit_usd"]))
            except (TypeError, ValueError):
                pass
        if raw.get("platform_markup") is not None:
            try:
                base["platform_markup"] = max(0.01, float(raw["platform_markup"]))
            except (TypeError, ValueError):
                pass
        base["updated_at"] = raw.get("updated_at")
        base["version"] = str(raw.get("version") or "1")

    _cache = base
    return deepcopy(base)


def save_billing_config(patch: dict[str, Any]) -> dict[str, Any]:
    global _cache
    current = get_billing_config(refresh=True)

    if "credit_usd" in patch and patch["credit_usd"] is not None:
        current["credit_usd"] = max(0.0001, float(patch["credit_usd"]))
    if "platform_markup" in patch and patch["platform_markup"] is not None:
        current["platform_markup"] = max(0.01, float(patch["platform_markup"]))

    if isinstance(patch.get("action_credits"), dict):
        for k, v in patch["action_credits"].items():
            current["action_credits"][str(k)] = max(0, int(v))

    if isinstance(patch.get("plans"), dict):
        for pid, plan in patch["plans"].items():
            if not isinstance(plan, dict):
                continue
            cur = current["plans"].setdefault(str(pid), {"id": str(pid)})
            for field in ("name", "description"):
                if field in plan and plan[field] is not None:
                    cur[field] = str(plan[field])
            if "credits" in plan:
                cur["credits"] = max(0, int(plan["credits"]))
            if "price_usd" in plan:
                cur["price_usd"] = None if plan["price_usd"] is None else float(plan["price_usd"])
            cur["id"] = str(pid)

    current["updated_at"] = _now()
    current["version"] = str(int(current.get("version") or "1") + 1) if str(current.get("version") or "").isdigit() else "2"
    get_blob_store().write_json(CONFIG_KEY, current)
    _cache = current
    return deepcopy(current)


def effective_plans() -> dict[str, dict[str, Any]]:
    return get_billing_config()["plans"]


def effective_action_credits(reason: str) -> int | None:
    cfg = get_billing_config()
    val = cfg.get("action_credits", {}).get(reason)
    if val is None:
        return None
    return int(val)
