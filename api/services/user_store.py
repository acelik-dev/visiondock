"""Persist and look up users from PostgreSQL / SQLite."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from db.models import FREE_PLAN_CREDITS, RefreshToken, User, UserSession
from services.password import hash_password, verify_password

VERIFY_TOKEN_HOURS = 48


def db_auth_enabled() -> bool:
    """Email/password accounts are always backed by the app DB (SQLite or Postgres)."""
    return os.getenv("AUTH_DB_USERS", "true").lower() not in ("0", "false", "no")


def signup_enabled() -> bool:
    if not db_auth_enabled():
        return False
    return os.getenv("AUTH_ALLOW_SIGNUP", "true").lower() not in ("0", "false", "no")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class UserStore:
    def upsert_google_user(
        self,
        db: Session,
        *,
        google_sub: str,
        email: str,
        name: str | None,
    ) -> User:
        now = datetime.now(timezone.utc)
        user = db.query(User).filter(User.google_sub == google_sub).one_or_none()
        if user is None:
            user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            user = User(
                email=email,
                name=name,
                google_sub=google_sub,
                last_login=now,
                credits_balance=FREE_PLAN_CREDITS,
                active_plan="free",
                email_verified_at=now,
            )
            db.add(user)
        else:
            user.email = email
            user.name = name or user.name
            user.google_sub = google_sub
            user.last_login = now
            if user.email_verified_at is None:
                user.email_verified_at = now
        db.commit()
        db.refresh(user)
        return user

    def upsert_microsoft_user(
        self,
        db: Session,
        *,
        microsoft_sub: str,
        email: str,
        name: str | None,
    ) -> User:
        now = datetime.now(timezone.utc)
        user = db.query(User).filter(User.microsoft_sub == microsoft_sub).one_or_none()
        if user is None:
            user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            user = User(
                email=email,
                name=name,
                microsoft_sub=microsoft_sub,
                last_login=now,
                credits_balance=FREE_PLAN_CREDITS,
                active_plan="free",
                email_verified_at=now,
            )
            db.add(user)
        else:
            user.email = email
            user.name = name or user.name
            user.microsoft_sub = microsoft_sub
            user.last_login = now
            if user.email_verified_at is None:
                user.email_verified_at = now
        db.commit()
        db.refresh(user)
        return user

    def register_email_user(
        self,
        db: Session,
        *,
        email: str,
        password: str,
        name: str | None = None,
    ) -> tuple[User, str]:
        """Create user + email verification token. Returns (user, raw_verify_token)."""
        normalized = email.strip().lower()
        existing = db.query(User).filter(User.email == normalized).one_or_none()
        if existing is not None:
            raise ValueError("An account with this email already exists")
        now = datetime.now(timezone.utc)
        raw_token = secrets.token_urlsafe(32)
        user = User(
            email=normalized,
            name=(name or "").strip() or None,
            password_hash=hash_password(password),
            last_login=now,
            credits_balance=FREE_PLAN_CREDITS,
            active_plan="free",
            email_verified_at=None,
            email_verify_token_hash=_hash_token(raw_token),
            email_verify_sent_at=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, raw_token

    def verify_email_token(self, db: Session, *, raw_token: str) -> User | None:
        token_hash = _hash_token(raw_token)
        user = (
            db.query(User)
            .filter(User.email_verify_token_hash == token_hash)
            .one_or_none()
        )
        if user is None:
            return None
        sent = user.email_verify_sent_at
        if sent is not None:
            if sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - sent > timedelta(hours=VERIFY_TOKEN_HOURS):
                return None
        now = datetime.now(timezone.utc)
        user.email_verified_at = now
        user.email_verify_token_hash = None
        db.commit()
        db.refresh(user)
        return user

    def issue_email_verify_token(self, db: Session, user: User) -> str:
        raw = secrets.token_urlsafe(32)
        user.email_verify_token_hash = _hash_token(raw)
        user.email_verify_sent_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return raw

    def authenticate_email_user(self, db: Session, *, email: str, password: str) -> User | None:
        normalized = email.strip().lower()
        user = db.query(User).filter(User.email == normalized).one_or_none()
        if user is None or not user.password_hash:
            return None
        if not verify_password(password, user.password_hash):
            return None
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    def create_refresh_token(
        self,
        db: Session,
        *,
        user_id: int,
        session_id: int | None = None,
        days: int = 30,
    ) -> str:
        raw = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw)
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        row = RefreshToken(
            user_id=user_id,
            session_id=session_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(row)
        db.commit()
        return raw

    def rotate_refresh_token(self, db: Session, *, raw_token: str) -> tuple[User, str, int | None] | None:
        token_hash = _hash_token(raw_token)
        now = datetime.now(timezone.utc)
        row = (
            db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .one_or_none()
        )
        if row is None or row.expires_at < now:
            return None
        if row.session_id is not None:
            sess = db.query(UserSession).filter(UserSession.id == row.session_id).one_or_none()
            if sess is None or sess.revoked_at is not None:
                row.revoked_at = now
                db.commit()
                return None
            if sess.expires_at is not None and sess.expires_at < now:
                sess.revoked_at = now
                row.revoked_at = now
                db.commit()
                return None
        user = db.query(User).filter(User.id == row.user_id).one_or_none()
        if user is None:
            return None
        row.revoked_at = now
        new_raw = self.create_refresh_token(
            db, user_id=user.id, session_id=row.session_id
        )
        user.last_login = now
        db.commit()
        db.refresh(user)
        return user, new_raw, row.session_id

    def revoke_refresh_token(self, db: Session, *, raw_token: str) -> None:
        token_hash = _hash_token(raw_token)
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).one_or_none()
        if row is not None:
            row.revoked_at = datetime.now(timezone.utc)
            db.commit()

    def revoke_session_tokens(self, db: Session, *, session_id: int) -> None:
        now = datetime.now(timezone.utc)
        rows = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.session_id == int(session_id),
                RefreshToken.revoked_at.is_(None),
            )
            .all()
        )
        for row in rows:
            row.revoked_at = now
        if rows:
            db.commit()

    def get_by_id(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).one_or_none()


_user_store: UserStore | None = None


def get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store
