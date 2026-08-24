"""SQLAlchemy database setup — SQLite for local dev, PostgreSQL in Azure."""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    # Azure App Service: never fall back to ephemeral SQLite under wwwroot.
    if os.getenv("WEBSITE_INSTANCE_ID") or os.getenv("WEBSITE_SITE_NAME"):
        raise RuntimeError(
            "DATABASE_URL is required on Azure App Service. "
            "Provision Postgres (scripts/azure-provision-postgres.sh) and set DATABASE_URL."
        )
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(api_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "visiondock.db")
    return f"sqlite:///{db_path}"


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if _is_sqlite(url) else {}
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def get_session_factory():
    get_engine()
    return _SessionLocal


def _ensure_schema() -> None:
    from sqlalchemy import inspect, text

    engine = get_engine()
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "users" in tables:
        cols = {c["name"] for c in insp.get_columns("users")}
        if "microsoft_sub" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN microsoft_sub VARCHAR(255)"))
        if "password_hash" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "credits_balance" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN credits_balance INTEGER NOT NULL DEFAULT 100"))
        if "active_plan" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN active_plan VARCHAR(32) NOT NULL DEFAULT 'free'"))
        if "email_verified_at" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP"))
        if "email_verify_token_hash" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verify_token_hash VARCHAR(64)"))
        if "email_verify_sent_at" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verify_sent_at TIMESTAMP"))
    if "user_sessions" in tables:
        cols = {c["name"] for c in insp.get_columns("user_sessions")}
        if "expires_at" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE user_sessions ADD COLUMN expires_at TIMESTAMP"))
    if "refresh_tokens" in tables:
        cols = {c["name"] for c in insp.get_columns("refresh_tokens")}
        if "session_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE refresh_tokens ADD COLUMN session_id INTEGER"))
    if "credit_ledger" in tables:
        cols = {c["name"] for c in insp.get_columns("credit_ledger")}
        if "azure_cost_usd" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE credit_ledger ADD COLUMN azure_cost_usd FLOAT"))
        if "usage_event_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE credit_ledger ADD COLUMN usage_event_id INTEGER"))


def init_db() -> None:
    from db.models import (  # noqa: F401
        CreditLedger,
        EmailMessage,
        RefreshToken,
        UsageEvent,
        User,
        UserSession,
    )

    Base.metadata.create_all(bind=get_engine())
    _ensure_schema()


def get_db() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
