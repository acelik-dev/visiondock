"""Admin access helpers — ADMIN_EMAILS env (comma-separated)."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from session_auth import SESSION_USER_KEY


def admin_emails() -> set[str]:
    raw = (os.getenv("ADMIN_EMAILS") or "").strip()
    emails = {part.strip().lower() for part in raw.split(",") if part.strip()}
    # Fall back to env login username so local admin still works.
    fallback = (os.getenv("AUTH_USERNAME") or os.getenv("BASIC_AUTH_USERNAME") or "").strip().lower()
    if fallback:
        emails.add(fallback)
    return emails


def session_email(request: Request) -> str:
    return (
        (request.session.get("email") or request.session.get(SESSION_USER_KEY) or "")
        .strip()
        .lower()
    )


def is_admin_request(request: Request) -> bool:
    email = session_email(request)
    if not email:
        return False
    allowed = admin_emails()
    if not allowed:
        return False
    return email in allowed


def require_admin(request: Request) -> str:
    email = session_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not is_admin_request(request):
        raise HTTPException(status_code=403, detail="Admin access required")
    return email
