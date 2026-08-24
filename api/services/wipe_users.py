"""One-shot / admin helpers to clear auth users for retesting."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("visiondock.wipe_users")


def wipe_all_users(*, wipe_projects: bool = True) -> dict[str, Any]:
    """Delete all users and auth-related rows. Optionally wipe blob projects too."""
    from db.database import get_session_factory, init_db
    from db.models import (
        CreditLedger,
        EmailMessage,
        RefreshToken,
        UsageEvent,
        User,
        UserSession,
    )

    init_db()
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        counts: dict[str, int] = {}
        # FK-safe order
        for model in (
            CreditLedger,
            UsageEvent,
            EmailMessage,
            RefreshToken,
            UserSession,
            User,
        ):
            n = db.query(model).delete()
            counts[model.__tablename__] = int(n)
        db.commit()
        logger.warning("Wiped auth data: %s", counts)
        result: dict[str, Any] = {"ok": True, "deleted": counts}
        if wipe_projects:
            result["projects"] = wipe_all_projects()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def wipe_all_projects() -> dict[str, Any]:
    """Delete every project from blob/index so a user wipe cannot leave orphan workspaces."""
    from services.project_store import ProjectStore

    store = ProjectStore()
    # Unfiltered index — wipe is admin-only / startup-only.
    rows = store.list_projects()
    deleted = 0
    errors: list[str] = []
    for row in rows:
        pid = row.get("id")
        if not pid:
            continue
        try:
            store.delete_project(str(pid))
            deleted += 1
        except Exception as exc:  # noqa: BLE001 — best-effort wipe
            errors.append(f"{pid}: {exc}")
            logger.warning("Failed to delete project %s: %s", pid, exc)
    logger.warning("Wiped projects: deleted=%s errors=%s", deleted, len(errors))
    return {"deleted": deleted, "errors": errors}

def maybe_wipe_users_on_startup() -> None:
    """If WIPE_ALL_USERS=1 (or true), wipe once at boot. Caller should unset the env after."""
    flag = os.getenv("WIPE_ALL_USERS", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return
    result = wipe_all_users()
    logger.warning("WIPE_ALL_USERS completed: %s", result)
