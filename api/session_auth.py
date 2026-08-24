"""Session cookie auth — no browser Basic Auth popup."""

from __future__ import annotations

import os
import secrets
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

SESSION_USER_KEY = "user"
SESSION_USER_ID_KEY = "user_id"
SESSION_DB_ID_KEY = "db_session_id"

PUBLIC_PREFIXES = ("/api/auth/", "/assets/")
PUBLIC_EXACT = {"/", "/favicon.svg", "/opengraph.jpg", "/api/health", "/api/training/info"}
STATIC_SUFFIXES = (".js", ".css", ".svg", ".jpg", ".jpeg", ".png", ".ico", ".woff2", ".map")


def google_oauth_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID")) and bool(os.getenv("GOOGLE_CLIENT_SECRET"))


def microsoft_oauth_configured() -> bool:
    return bool(os.getenv("MICROSOFT_CLIENT_ID")) and bool(os.getenv("MICROSOFT_CLIENT_SECRET"))


def password_auth_configured() -> bool:
    from services.user_store import db_auth_enabled

    if db_auth_enabled():
        return True
    return bool(_expected_username()) and bool(_expected_password())


def email_verify_required() -> bool:
    return os.getenv("AUTH_REQUIRE_EMAIL_VERIFY", "true").lower() not in ("0", "false", "no")


def signup_enabled() -> bool:
    from services.user_store import signup_enabled as _signup_enabled

    return _signup_enabled()


def auth_enabled() -> bool:
    if os.getenv("AUTH_ENABLED", os.getenv("BASIC_AUTH_ENABLED", "true")).lower() in (
        "0",
        "false",
        "no",
    ):
        return False
    if google_oauth_configured() or microsoft_oauth_configured():
        return True
    return password_auth_configured()


def _expected_username() -> str:
    return os.getenv("AUTH_USERNAME") or os.getenv("BASIC_AUTH_USERNAME") or ""


def _expected_password() -> str:
    return os.getenv("AUTH_PASSWORD") or os.getenv("BASIC_AUTH_PASSWORD") or ""


def session_secret() -> str:
    secret = os.getenv("AUTH_SESSION_SECRET") or os.getenv("SESSION_SECRET")
    if secret:
        return secret
    return "dev-only-change-me-in-production"


def verify_credentials(username: str, password: str) -> bool:
    expected_user = _expected_username()
    expected_pass = _expected_password()
    if not expected_user or not expected_pass:
        return False
    user_ok = secrets.compare_digest(username, expected_user)
    pass_ok = secrets.compare_digest(password, expected_pass)
    return user_ok and pass_ok


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return True
    return path.endswith(STATIC_SUFFIXES)


class SessionAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._enabled = auth_enabled()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._enabled:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if _is_public_path(request.url.path):
            return await call_next(request)

        if request.session.get(SESSION_USER_KEY):
            # Cookie session must still map to an active DB session when present.
            db_sid = request.session.get(SESSION_DB_ID_KEY)
            user_id = request.session.get(SESSION_USER_ID_KEY)
            if request.url.path.startswith("/api/") and (db_sid is not None or user_id is not None):
                try:
                    from db.database import get_session_factory
                    from db.models import User
                    from services.user_sessions import get_active_session

                    SessionLocal = get_session_factory()
                    db = SessionLocal()
                    try:
                        if db_sid is not None:
                            active = get_active_session(db, int(db_sid))
                            if active is None:
                                request.session.clear()
                                return JSONResponse(
                                    status_code=401,
                                    content={"detail": "Session expired or revoked"},
                                )
                        if email_verify_required() and user_id is not None:
                            user = db.query(User).filter(User.id == int(user_id)).one_or_none()
                            if user is not None and user.email_verified_at is None:
                                request.session.clear()
                                return JSONResponse(
                                    status_code=403,
                                    content={
                                        "detail": (
                                            "Email not verified. Check your inbox for the "
                                            "confirmation link before signing in."
                                        ),
                                        "code": "email_unverified",
                                    },
                                )
                    finally:
                        db.close()
                except Exception:
                    pass
            return await call_next(request)

        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        return await call_next(request)


def install_session_auth(app) -> None:
    https_only = bool(os.getenv("WEBSITE_HOSTNAME")) or os.getenv("ENVIRONMENT") == "production"
    app.add_middleware(SessionAuthMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(),
        https_only=https_only,
        same_site="lax",
    )
