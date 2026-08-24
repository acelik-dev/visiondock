"""Per-user project ownership checks."""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request

from session_auth import SESSION_DB_ID_KEY, SESSION_USER_ID_KEY, SESSION_USER_KEY


def session_user(request: Request) -> dict[str, Any]:
    email = (request.session.get(SESSION_USER_KEY) or request.session.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = request.session.get(SESSION_USER_ID_KEY)
    db_session_id = request.session.get(SESSION_DB_ID_KEY)
    return {
        "email": email.lower(),
        "user_id": user_id,
        "session_id": db_session_id,
    }


def _legacy_owner_email() -> str:
    return (os.getenv("AUTH_USERNAME") or os.getenv("BASIC_AUTH_USERNAME") or "").strip().lower()


def user_owns_project(meta: dict[str, Any], user: dict[str, Any]) -> bool:
    owner_id = meta.get("owner_user_id")
    owner_email = (meta.get("owner_email") or "").strip().lower()
    session_email = user["email"]
    session_id = user.get("user_id")

    # Email is authoritative when set — prevents user_id reuse after wipe from
    # granting access to another account's projects (or stale same-id rows).
    if owner_email and owner_email != session_email:
        return False

    if owner_id is not None and session_id is not None:
        return int(owner_id) == int(session_id)
    if owner_email:
        return owner_email == session_email
    legacy = _legacy_owner_email()
    if legacy:
        return session_email == legacy
    return False


def require_project_access(meta: dict[str, Any] | None, project_id: str, user: dict[str, Any]) -> dict[str, Any]:
    if meta is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not user_owns_project(meta, user):
        raise HTTPException(status_code=404, detail="Project not found")
    return meta


def owner_fields(user: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {"owner_email": user["email"]}
    if user.get("user_id") is not None:
        fields["owner_user_id"] = int(user["user_id"])
    return fields
