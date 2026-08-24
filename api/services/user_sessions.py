"""Persist login sessions and usage events for credit attribution."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from db.models import UsageEvent, UserSession
from session_auth import SESSION_DB_ID_KEY


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def session_ttl_days() -> int:
    try:
        return max(1, int(os.getenv("AUTH_SESSION_DAYS", "30") or "30"))
    except ValueError:
        return 30


def create_login_session(
    db: Session,
    *,
    user_id: int,
    auth_method: str,
    request: Request | None = None,
) -> UserSession:
    ua = None
    ip = None
    if request is not None:
        ua = (request.headers.get("user-agent") or "")[:512] or None
        ip = (request.client.host if request.client else None) or None
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()[:64] or ip
    now = _utcnow()
    row = UserSession(
        user_id=int(user_id),
        auth_method=(auth_method or "password")[:32],
        user_agent=ua,
        ip_hint=ip,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=session_ttl_days()),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if request is not None:
        request.session[SESSION_DB_ID_KEY] = row.id
    return row


def get_active_session(db: Session, session_id: int | None) -> UserSession | None:
    if session_id is None:
        return None
    row = db.query(UserSession).filter(UserSession.id == int(session_id)).one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    now = _utcnow()
    exp = row.expires_at
    if exp is not None:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            row.revoked_at = now
            db.commit()
            return None
    return row


def revoke_login_session(db: Session, request: Request) -> None:
    sid = request.session.get(SESSION_DB_ID_KEY)
    if not sid:
        return
    row = db.query(UserSession).filter(UserSession.id == int(sid)).one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.commit()
        try:
            from services.user_store import get_user_store

            get_user_store().revoke_session_tokens(db, session_id=int(sid))
        except Exception:
            pass


def revoke_session_for_user(
    db: Session,
    *,
    user_id: int,
    session_id: int,
) -> bool:
    row = (
        db.query(UserSession)
        .filter(UserSession.id == int(session_id), UserSession.user_id == int(user_id))
        .one_or_none()
    )
    if row is None:
        return False
    if row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.commit()
        try:
            from services.user_store import get_user_store

            get_user_store().revoke_session_tokens(db, session_id=int(session_id))
        except Exception:
            pass
    return True


def list_sessions_for_user(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(UserSession)
        .filter(UserSession.user_id == int(user_id))
        .order_by(UserSession.created_at.desc())
        .limit(50)
        .all()
    )
    now = _utcnow()
    out: list[dict[str, Any]] = []
    for row in rows:
        expired = False
        if row.expires_at is not None:
            exp = row.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            expired = exp < now
        active = row.revoked_at is None and not expired
        out.append(
            {
                "id": row.id,
                "auth_method": row.auth_method,
                "user_agent": row.user_agent,
                "ip_hint": row.ip_hint,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                "active": active,
            }
        )
    return out


def touch_login_session(db: Session, session_id: int | None) -> None:
    row = get_active_session(db, session_id)
    if row is None:
        return
    row.last_seen_at = _utcnow()
    db.commit()


def record_usage_event(
    db: Session,
    *,
    user_id: int,
    action: str,
    status: str = "success",
    credits_delta: int = 0,
    azure_cost_usd: float | None = None,
    project_id: str | None = None,
    ref: str | None = None,
    note: str | None = None,
    session_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> UsageEvent:
    row = UsageEvent(
        user_id=int(user_id),
        session_id=int(session_id) if session_id is not None else None,
        action=action[:64],
        status=(status or "success")[:32],
        credits_delta=int(credits_delta),
        azure_cost_usd=azure_cost_usd,
        project_id=(project_id or None),
        ref=ref,
        note=note,
        meta_json=json.dumps(meta) if meta else None,
    )
    db.add(row)
    db.flush()
    return row
