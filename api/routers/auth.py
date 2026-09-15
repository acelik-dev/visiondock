"""Auth routes — DB sessions, OAuth, email sign-up with welcome mail, refresh tokens."""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from services.email_service import email_configured, send_welcome_email
from services.user_store import get_user_store, signup_enabled
from services.user_sessions import (
    create_login_session,
    get_active_session,
    list_sessions_for_user,
    revoke_login_session,
    revoke_session_for_user,
    touch_login_session,
)
from session_auth import (
    SESSION_DB_ID_KEY,
    SESSION_USER_ID_KEY,
    SESSION_USER_KEY,
    auth_enabled,
    email_verify_required,
    google_oauth_configured,
    microsoft_oauth_configured,
    password_auth_configured,
    verify_credentials,
)

logger = logging.getLogger("visiondock.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
MICROSOFT_GRAPH_ME_URL = "https://graph.microsoft.com/v1.0/me"
OAUTH_STATE_KEY = "oauth_state"
MICROSOFT_OAUTH_STATE_KEY = "microsoft_oauth_state"
REFRESH_COOKIE = "visiondock_refresh"


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=255)


class ResendVerificationRequest(BaseModel):
    email: str


def _oauth_redirect_uri(provider: str) -> str:
    env_key = "OAUTH_REDIRECT_URI" if provider == "google" else "MICROSOFT_REDIRECT_URI"
    explicit = os.getenv(env_key, "").strip()
    if explicit:
        return explicit
    hostname = os.getenv("WEBSITE_HOSTNAME", "").strip()
    if hostname:
        return f"https://{hostname}/api/auth/{provider}/callback"
    return f"http://localhost:8000/api/auth/{provider}/callback"


def _microsoft_tenant() -> str:
    return os.getenv("AZURE_TENANT_ID", "common").strip() or "common"


def _frontend_url() -> str:
    url = os.getenv("FRONTEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    hostname = os.getenv("WEBSITE_HOSTNAME", "").strip()
    if hostname:
        return f"https://{hostname}"
    return "http://localhost:8080"


def _cookie_secure() -> bool:
    return bool(os.getenv("WEBSITE_HOSTNAME")) or os.getenv("ENVIRONMENT") == "production"


def _session_user_payload(request: Request, *, email_verified: bool | None = None) -> dict:
    user = request.session.get(SESSION_USER_KEY)
    if not user:
        return {"authenticated": False}
    from services.admin_access import is_admin_request

    payload = {
        "authenticated": True,
        "username": user,
        "email": request.session.get("email") or user,
        "name": request.session.get("name"),
        "user_id": request.session.get(SESSION_USER_ID_KEY),
        "session_id": request.session.get(SESSION_DB_ID_KEY),
        "auth_method": request.session.get("auth_method"),
        "is_admin": is_admin_request(request),
    }
    if email_verified is not None:
        payload["email_verified"] = email_verified
    elif "email_verified" in request.session:
        payload["email_verified"] = bool(request.session.get("email_verified"))
    return payload


def _set_session_user(
    request: Request,
    *,
    email: str,
    name: str | None = None,
    user_id: int | None = None,
    auth_method: str,
    db: Session | None = None,
    mint_db_session: bool = True,
    email_verified: bool | None = None,
) -> None:
    request.session[SESSION_USER_KEY] = email
    request.session["email"] = email
    request.session["name"] = name
    request.session["auth_method"] = auth_method
    if email_verified is not None:
        request.session["email_verified"] = email_verified
    if user_id is not None:
        request.session[SESSION_USER_ID_KEY] = user_id
    if db is not None and user_id is not None:
        if mint_db_session:
            request.session.pop(SESSION_DB_ID_KEY, None)
            create_login_session(
                db,
                user_id=int(user_id),
                auth_method=auth_method,
                request=request,
            )
        elif not request.session.get(SESSION_DB_ID_KEY):
            create_login_session(
                db,
                user_id=int(user_id),
                auth_method=auth_method,
                request=request,
            )


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=30 * 24 * 60 * 60,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/auth")


def _login_db_user(
    request: Request,
    db: Session,
    user,
    *,
    auth_method: str = "password",
    extra: dict | None = None,
) -> JSONResponse:
    verified = user.email_verified_at is not None
    _set_session_user(
        request,
        email=user.email,
        name=user.name,
        user_id=user.id,
        auth_method=auth_method,
        db=db,
        email_verified=verified,
    )
    session_id = request.session.get(SESSION_DB_ID_KEY)
    raw_refresh = get_user_store().create_refresh_token(
        db,
        user_id=user.id,
        session_id=int(session_id) if session_id is not None else None,
    )
    payload = _session_user_payload(request, email_verified=verified)
    if extra:
        payload.update(extra)
    response = JSONResponse(payload)
    _set_refresh_cookie(response, raw_refresh)
    return response


@router.get("/config")
async def auth_config():
    return {
        "auth_enabled": auth_enabled(),
        "google": google_oauth_configured(),
        "microsoft": microsoft_oauth_configured(),
        "password": password_auth_configured(),
        "signup": signup_enabled(),
        "email_delivery": email_configured(),
        "email_verify_required": email_verify_required(),
    }


@router.get("/me")
async def auth_me(request: Request, db: Session = Depends(get_db)):
    payload = _session_user_payload(request)
    if not payload.get("authenticated"):
        return payload
    sid = request.session.get(SESSION_DB_ID_KEY)
    if sid is not None:
        active = get_active_session(db, int(sid))
        if active is None:
            request.session.clear()
            return {"authenticated": False, "detail": "Session expired or revoked"}
        touch_login_session(db, int(sid))
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if user_id is not None:
        user = get_user_store().get_by_id(db, int(user_id))
        if user is not None:
            verified = user.email_verified_at is not None
            payload["email_verified"] = verified
            request.session["email_verified"] = verified
            if email_verify_required() and not verified:
                request.session.clear()
                return {
                    "authenticated": False,
                    "detail": "Email not verified",
                    "code": "email_unverified",
                    "email": user.email,
                }
    return payload


@router.post("/register")
async def auth_register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)):
    if not signup_enabled():
        raise HTTPException(status_code=403, detail="Sign-up is not enabled")
    store = get_user_store()
    try:
        user, verify_token = store.register_email_user(
            db,
            email=body.email,
            password=body.password,
            name=body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    mail = send_welcome_email(db, user=user, verify_token=verify_token)
    if not mail.get("ok"):
        logger.warning("Welcome email failed for %s: %s", user.email, mail.get("error"))

    # Do not open an app session until the email is confirmed.
    request.session.clear()
    return {
        "authenticated": False,
        "email": user.email,
        "email_sent": bool(mail.get("ok")),
        "email_status": mail.get("status"),
        "email_verified": False,
        "requires_email_verification": True,
        "message": (
            f"Account created. Confirm the link we sent to {user.email} before signing in."
            if mail.get("ok")
            else (
                f"Account created, but the confirmation email failed ({mail.get('status')}). "
                "Use Resend verification after fixing email delivery."
            )
        ),
    }


@router.post("/login")
async def auth_login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    if not auth_enabled():
        _set_session_user(request, email=body.username or "dev", auth_method="dev")
        return _session_user_payload(request)
    if not password_auth_configured():
        raise HTTPException(status_code=400, detail="Password sign-in is not configured")

    user = get_user_store().authenticate_email_user(
        db, email=body.username, password=body.password
    )
    if user is not None:
        if email_verify_required() and user.email_verified_at is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": (
                        "Email not verified. Open the confirmation link we sent you, "
                        "then sign in."
                    ),
                    "code": "email_unverified",
                    "email": user.email,
                },
            )
        return _login_db_user(request, db, user)

    if verify_credentials(body.username, body.password):
        _set_session_user(request, email=body.username, auth_method="password")
        # JSONResponse so SessionMiddleware reliably attaches the session cookie
        # (same path as DB login); plain dicts can leave the browser without a session.
        return JSONResponse(_session_user_payload(request))

    raise HTTPException(status_code=401, detail="Invalid email or password")


@router.post("/refresh")
async def auth_refresh(request: Request, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    rotated = get_user_store().rotate_refresh_token(db, raw_token=raw)
    if rotated is None:
        response = JSONResponse(status_code=401, content={"detail": "Invalid refresh token"})
        _clear_refresh_cookie(response)
        return response
    user, new_raw, session_id = rotated
    if session_id is not None:
        request.session[SESSION_DB_ID_KEY] = session_id
    _set_session_user(
        request,
        email=user.email,
        name=user.name,
        user_id=user.id,
        auth_method=request.session.get("auth_method") or "password",
        db=db,
        mint_db_session=False,
        email_verified=user.email_verified_at is not None,
    )
    payload = _session_user_payload(
        request, email_verified=user.email_verified_at is not None
    )
    response = JSONResponse(payload)
    _set_refresh_cookie(response, new_raw)
    return response


@router.post("/logout")
async def auth_logout(request: Request, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        get_user_store().revoke_refresh_token(db, raw_token=raw)
    try:
        revoke_login_session(db, request)
    except Exception:
        logger.debug("revoke_login_session failed", exc_info=True)
    request.session.clear()
    response = JSONResponse({"authenticated": False})
    _clear_refresh_cookie(response)
    return response


@router.get("/sessions")
async def auth_sessions(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not request.session.get(SESSION_USER_KEY) or user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    current = request.session.get(SESSION_DB_ID_KEY)
    rows = list_sessions_for_user(db, int(user_id))
    for row in rows:
        row["current"] = current is not None and row["id"] == int(current)
    return {"success": True, "data": {"sessions": rows, "current_session_id": current}}


@router.delete("/sessions/{session_id}")
async def auth_revoke_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not request.session.get(SESSION_USER_KEY) or user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    ok = revoke_session_for_user(db, user_id=int(user_id), session_id=int(session_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    if request.session.get(SESSION_DB_ID_KEY) == session_id:
        request.session.clear()
        response = JSONResponse({"success": True, "logged_out": True})
        _clear_refresh_cookie(response)
        return response
    return {"success": True, "logged_out": False}


@router.get("/verify-email")
async def auth_verify_email(token: str, request: Request, db: Session = Depends(get_db)):
    if not token or len(token) < 16:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    user = get_user_store().verify_email_token(db, raw_token=token)
    if user is None:
        return RedirectResponse(f"{_frontend_url()}/?auth_error=verify_failed")
    # After confirm, open a session so the user lands in the app.
    _set_session_user(
        request,
        email=user.email,
        name=user.name,
        user_id=user.id,
        auth_method="password",
        db=db,
        email_verified=True,
    )
    sid = request.session.get(SESSION_DB_ID_KEY)
    raw_refresh = get_user_store().create_refresh_token(
        db, user_id=user.id, session_id=int(sid) if sid is not None else None
    )
    response = RedirectResponse(f"{_frontend_url()}/?email_verified=1&fresh_login=1")
    _set_refresh_cookie(response, raw_refresh)
    return response


@router.post("/resend-verification")
async def auth_resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    store = get_user_store()
    user = None
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if user_id is not None:
        user = store.get_by_id(db, int(user_id))
    if user is None and body.email:
        from db.models import User

        user = db.query(User).filter(User.email == body.email.strip().lower()).one_or_none()
    if user is None:
        return {
            "success": True,
            "data": {"email_sent": True, "note": "If that account exists, a mail was sent."},
        }
    if user.email_verified_at is not None:
        return {"success": True, "data": {"already_verified": True}}
    raw = store.issue_email_verify_token(db, user)
    mail = send_welcome_email(db, user=user, verify_token=raw)
    return {
        "success": True,
        "data": {
            "email_sent": bool(mail.get("ok")),
            "email_status": mail.get("status"),
            "to": user.email,
        },
    }


@router.post("/admin/wipe-users")
async def auth_admin_wipe_users(request: Request):
    """One-shot wipe for retesting. Requires header X-Admin-Wipe-Secret == ADMIN_WIPE_SECRET."""
    expected = os.getenv("ADMIN_WIPE_SECRET", "").strip()
    provided = (request.headers.get("X-Admin-Wipe-Secret") or "").strip()
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=404, detail="Not found")
    from services.wipe_users import wipe_all_users

    return {"success": True, "data": wipe_all_users()}


@router.get("/google/login")
async def google_login(request: Request):
    if not google_oauth_configured():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    state = secrets.token_urlsafe(32)
    request.session[OAUTH_STATE_KEY] = state
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": _oauth_redirect_uri("google"),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(f"{_frontend_url()}/?auth_error={error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state")
    expected_state = request.session.pop(OAUTH_STATE_KEY, None)
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    redirect_uri = _oauth_redirect_uri("google")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                logger.error("Google token exchange failed: %s", token_resp.text)
                raise HTTPException(status_code=502, detail="Google sign-in failed")
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="Google sign-in failed")

            user_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                logger.error("Google userinfo failed: %s", user_resp.text)
                raise HTTPException(status_code=502, detail="Google sign-in failed")
            profile = user_resp.json()
    except httpx.HTTPError as exc:
        logger.exception("Google OAuth HTTP error: %s", exc)
        raise HTTPException(status_code=502, detail="Google sign-in failed") from exc

    google_sub = profile.get("sub")
    email = profile.get("email")
    if not google_sub or not email:
        raise HTTPException(status_code=502, detail="Google account email is required")

    user = get_user_store().upsert_google_user(
        db,
        google_sub=google_sub,
        email=email,
        name=profile.get("name"),
    )
    _set_session_user(
        request,
        email=user.email,
        name=user.name,
        user_id=user.id,
        auth_method="google",
        db=db,
        email_verified=True,
    )
    sid = request.session.get(SESSION_DB_ID_KEY)
    raw_refresh = get_user_store().create_refresh_token(
        db, user_id=user.id, session_id=int(sid) if sid is not None else None
    )
    response = RedirectResponse(f"{_frontend_url()}/?fresh_login=1")
    _set_refresh_cookie(response, raw_refresh)
    return response


@router.get("/microsoft/login")
async def microsoft_login(request: Request):
    if not microsoft_oauth_configured():
        raise HTTPException(status_code=503, detail="Microsoft sign-in is not configured")
    state = secrets.token_urlsafe(32)
    request.session[MICROSOFT_OAUTH_STATE_KEY] = state
    tenant = _microsoft_tenant()
    params = {
        "client_id": os.environ["MICROSOFT_CLIENT_ID"],
        "redirect_uri": _oauth_redirect_uri("microsoft"),
        "response_type": "code",
        "scope": "openid profile email User.Read",
        "state": state,
        "response_mode": "query",
        "prompt": "select_account",
    }
    auth_url = MICROSOFT_AUTH_URL.format(tenant=tenant)
    return RedirectResponse(f"{auth_url}?{urlencode(params)}")


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        logger.warning("Microsoft OAuth error: %s", error)
        return RedirectResponse(f"{_frontend_url()}/?auth_error={error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth code or state")
    expected_state = request.session.pop(MICROSOFT_OAUTH_STATE_KEY, None)
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    client_id = os.environ["MICROSOFT_CLIENT_ID"]
    client_secret = os.environ["MICROSOFT_CLIENT_SECRET"]
    redirect_uri = _oauth_redirect_uri("microsoft")
    tenant = _microsoft_tenant()
    token_url = MICROSOFT_TOKEN_URL.format(tenant=tenant)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_resp = await client.post(
                token_url,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                logger.error("Microsoft token exchange failed: %s", token_resp.text)
                raise HTTPException(status_code=502, detail="Microsoft sign-in failed")
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="Microsoft sign-in failed")

            user_resp = await client.get(
                MICROSOFT_GRAPH_ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                logger.error("Microsoft Graph /me failed: %s", user_resp.text)
                raise HTTPException(status_code=502, detail="Microsoft sign-in failed")
            profile = user_resp.json()
    except httpx.HTTPError as exc:
        logger.exception("Microsoft OAuth HTTP error: %s", exc)
        raise HTTPException(status_code=502, detail="Microsoft sign-in failed") from exc

    microsoft_sub = profile.get("id")
    email = profile.get("mail") or profile.get("userPrincipalName")
    if not microsoft_sub or not email:
        raise HTTPException(status_code=502, detail="Microsoft account email is required")

    user = get_user_store().upsert_microsoft_user(
        db,
        microsoft_sub=microsoft_sub,
        email=email,
        name=profile.get("displayName"),
    )
    _set_session_user(
        request,
        email=user.email,
        name=user.name,
        user_id=user.id,
        auth_method="microsoft",
        db=db,
        email_verified=True,
    )
    sid = request.session.get(SESSION_DB_ID_KEY)
    raw_refresh = get_user_store().create_refresh_token(
        db, user_id=user.id, session_id=int(sid) if sid is not None else None
    )
    response = RedirectResponse(f"{_frontend_url()}/?fresh_login=1")
    _set_refresh_cookie(response, raw_refresh)
    return response
