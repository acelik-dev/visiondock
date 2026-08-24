"""Outbound transactional email (SMTP) for signup welcome / verify."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage as StdEmailMessage
from typing import Any

from sqlalchemy.orm import Session

from db.models import EmailMessage, User

logger = logging.getLogger("visiondock.email")

# In-memory capture for tests / local when SMTP is unset.
_LAST_SENT: list[dict[str, Any]] = []


def email_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip()) and bool(os.getenv("EMAIL_FROM", "").strip())


def clear_captured_emails() -> None:
    _LAST_SENT.clear()


def captured_emails() -> list[dict[str, Any]]:
    return list(_LAST_SENT)


def _frontend_url() -> str:
    url = os.getenv("FRONTEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    hostname = os.getenv("WEBSITE_HOSTNAME", "").strip()
    if hostname:
        return f"https://{hostname}"
    return "http://localhost:8080"


def _api_public_url() -> str:
    url = os.getenv("PUBLIC_API_URL", "").strip()
    if url:
        return url.rstrip("/")
    hostname = os.getenv("WEBSITE_HOSTNAME", "").strip()
    if hostname:
        return f"https://{hostname}"
    return "http://localhost:8000"


def build_verify_url(raw_token: str) -> str:
    return f"{_api_public_url()}/api/auth/verify-email?token={raw_token}"


def _smtp_send(*, to_email: str, subject: str, text_body: str, html_body: str) -> str | None:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_addr = os.getenv("EMAIL_FROM", "").strip()
    from_name = os.getenv("EMAIL_FROM_NAME", "VisionDock").strip() or "VisionDock"
    use_ssl = os.getenv("SMTP_SSL", "").lower() in ("1", "true", "yes")
    use_tls = os.getenv("SMTP_STARTTLS", "true").lower() not in ("0", "false", "no")

    msg = StdEmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            if use_tls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    return None


def _welcome_bodies(*, name: str | None, email: str, verify_url: str | None) -> tuple[str, str, str]:
    display = (name or "").strip() or email.split("@")[0]
    subject = "Welcome to VisionDock"
    verify_block_text = ""
    verify_block_html = ""
    if verify_url:
        verify_block_text = (
            f"\nConfirm your email to secure your account:\n{verify_url}\n"
            "This link expires in 48 hours.\n"
        )
        verify_block_html = f"""
        <p style="margin:24px 0;">
          <a href="{verify_url}"
             style="background:#0f172a;color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">
            Confirm email
          </a>
        </p>
        <p style="color:#64748b;font-size:13px;">Or open: {verify_url}<br/>Link expires in 48 hours.</p>
        """
    text = (
        f"Hi {display},\n\n"
        "Welcome to VisionDock — your no-code computer vision workspace.\n"
        f"Your account ({email}) is ready. You start with Free plan credits.\n"
        f"{verify_block_text}\n"
        f"Open the app: {_frontend_url()}\n\n"
        "— VisionDock\n"
    )
    html = f"""
    <div style="font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:560px;margin:0 auto;color:#0f172a;">
      <h1 style="font-size:22px;margin-bottom:8px;">Welcome to VisionDock</h1>
      <p>Hi {display},</p>
      <p>Your account (<strong>{email}</strong>) is ready. You start with Free plan credits for discovery, training, and inference.</p>
      {verify_block_html}
      <p><a href="{_frontend_url()}" style="color:#1d4ed8;">Open VisionDock</a></p>
      <p style="color:#94a3b8;font-size:12px;margin-top:32px;">— VisionDock</p>
    </div>
    """
    return subject, text, html


def send_and_log(
    db: Session,
    *,
    user: User | None,
    to_email: str,
    template: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> dict[str, Any]:
    row = EmailMessage(
        user_id=user.id if user is not None else None,
        to_email=to_email.strip().lower(),
        subject=subject[:255],
        template=template[:64],
        status="queued",
    )
    db.add(row)
    db.flush()

    payload = {
        "id": row.id,
        "to": to_email,
        "subject": subject,
        "template": template,
        "text": text_body,
        "html": html_body,
    }

    try:
        if email_configured():
            _smtp_send(
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
            row.status = "sent"
            row.sent_at = datetime.now(timezone.utc)
        else:
            # Dev / test: capture instead of dropping silently.
            row.status = "captured"
            row.sent_at = datetime.now(timezone.utc)
            logger.info(
                "EMAIL_CAPTURED template=%s to=%s subject=%s (set SMTP_HOST + EMAIL_FROM to send)",
                template,
                to_email,
                subject,
            )
        _LAST_SENT.append(payload)
        db.commit()
        db.refresh(row)
        return {
            "ok": True,
            "status": row.status,
            "email_message_id": row.id,
            "configured": email_configured(),
        }
    except Exception as exc:
        logger.exception("Failed to send email to %s: %s", to_email, exc)
        row.status = "failed"
        row.error = str(exc)[:2000]
        db.commit()
        return {
            "ok": False,
            "status": "failed",
            "email_message_id": row.id,
            "error": str(exc),
            "configured": email_configured(),
        }


def send_welcome_email(
    db: Session,
    *,
    user: User,
    verify_token: str | None = None,
) -> dict[str, Any]:
    verify_url = build_verify_url(verify_token) if verify_token else None
    subject, text_body, html_body = _welcome_bodies(
        name=user.name,
        email=user.email,
        verify_url=verify_url,
    )
    return send_and_log(
        db,
        user=user,
        to_email=user.email,
        template="welcome_verify",
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )
