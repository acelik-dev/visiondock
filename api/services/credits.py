"""Credit balance, plans, and ledger for VisionDock usage metering.

Fixed actions use Azure list-price estimates. Training is reserved at submit
and settled from real Azure ML job duration when the job ends.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from db.models import FREE_PLAN_CREDITS, CreditLedger, UsageEvent, User
from services.azure_pricing import (
    action_azure_usd,
    action_credits,
    pricing_catalog,
    training_compute_credits,
)
from services.project_access import session_user
from services.user_sessions import record_usage_event

logger = logging.getLogger(__name__)

# Display / reserve amounts derived from Azure pricing (not hard-coded demo values).
COSTS: dict[str, int] = {
    "vlm_analyze": action_credits("vlm_analyze"),
    "generate_config": action_credits("generate_config"),
    "pipeline_tune": action_credits("pipeline_tune"),
    "training_submit": action_credits("training_submit"),
    "inference_deploy": action_credits("inference_deploy"),
    "inference_predict": action_credits("inference_predict"),
}

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "credits": FREE_PLAN_CREDITS,
        "price_usd": None,
        "description": "Default starter credits. Membership pricing TBD.",
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "credits": 500,
        "price_usd": None,
        "description": "Default package — membership price set later.",
    },
    "pro": {
        "id": "pro",
        "name": "Professional",
        "credits": 2000,
        "price_usd": None,
        "description": "Default package — membership price set later.",
    },
}


class InsufficientCreditsError(Exception):
    def __init__(self, required: int, balance: int, reason: str):
        self.required = required
        self.balance = balance
        self.reason = reason
        super().__init__(
            f"Insufficient credits: need {required} for {reason}, have {balance}"
        )


def cost_for(reason: str) -> int:
    if reason in COSTS:
        return COSTS[reason]
    # Recompute dynamic actions (e.g. after env change) without restart gaps.
    try:
        return action_credits(reason)
    except Exception as exc:
        raise ValueError(f"Unknown credit reason: {reason}") from exc


def ensure_user_row(db: Session, session: dict[str, Any]) -> User:
    """Resolve or create a DB user for the current session."""
    user_id = session.get("user_id")
    email = (session.get("email") or "").strip().lower()
    if user_id:
        user = db.query(User).filter(User.id == int(user_id)).one_or_none()
        if user is not None:
            return user
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(
            email=email,
            name=email.split("@")[0],
            credits_balance=FREE_PLAN_CREDITS,
            active_plan="free",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _append_ledger(
            db,
            user,
            delta=FREE_PLAN_CREDITS,
            reason="signup_grant",
            note="Initial Free plan credits",
        )
        record_usage_event(
            db,
            user_id=user.id,
            action="signup_grant",
            status="success",
            credits_delta=FREE_PLAN_CREDITS,
            note="Initial Free plan credits",
            session_id=session.get("session_id"),
        )
        db.commit()
        db.refresh(user)
    return user


def get_account(db: Session, session: dict[str, Any]) -> dict[str, Any]:
    user = ensure_user_row(db, session)
    recent = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user.id)
        .order_by(CreditLedger.created_at.desc())
        .limit(30)
        .all()
    )
    usage = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == user.id)
        .order_by(UsageEvent.created_at.desc())
        .limit(40)
        .all()
    )
    catalog = pricing_catalog()
    return {
        "user_id": user.id,
        "email": user.email,
        "balance": int(user.credits_balance or 0),
        "plan": user.active_plan or "free",
        "session_id": session.get("session_id"),
        "plans": list(PLANS.values()),
        "costs": dict(catalog["costs"]),
        "pricing": {
            "credit_usd": catalog["credit_usd"],
            "platform_markup": catalog["platform_markup"],
            "region_note": catalog["region_note"],
            "vm_size": catalog["vm_size"],
            "vm_hourly_usd": catalog["vm_hourly_usd"],
            "training_billing": catalog["training_billing"],
            "cost_notes": catalog["cost_notes"],
        },
        "ledger": [
            {
                "id": row.id,
                "delta": row.delta,
                "balance_after": row.balance_after,
                "reason": row.reason,
                "ref": row.ref,
                "note": row.note,
                "azure_cost_usd": row.azure_cost_usd,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in recent
        ],
        "usage": [
            {
                "id": row.id,
                "action": row.action,
                "status": row.status,
                "credits_delta": row.credits_delta,
                "azure_cost_usd": row.azure_cost_usd,
                "project_id": row.project_id,
                "ref": row.ref,
                "note": row.note,
                "session_id": row.session_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in usage
        ],
    }


def _append_ledger(
    db: Session,
    user: User,
    *,
    delta: int,
    reason: str,
    ref: str | None = None,
    note: str | None = None,
    azure_cost_usd: float | None = None,
    usage_event_id: int | None = None,
) -> CreditLedger:
    row = CreditLedger(
        user_id=user.id,
        delta=delta,
        balance_after=int(user.credits_balance),
        reason=reason,
        ref=ref,
        note=note,
        azure_cost_usd=azure_cost_usd,
        usage_event_id=usage_event_id,
    )
    db.add(row)
    return row


def require_balance(
    db: Session,
    session: dict[str, Any],
    reason: str,
    *,
    amount: int | None = None,
) -> dict[str, Any]:
    """Ensure the user can afford an action without debiting yet."""
    cost = amount if amount is not None else cost_for(reason)
    user = ensure_user_row(db, session)
    balance = int(user.credits_balance or 0)
    if balance < cost:
        raise HTTPException(
            status_code=402,
            detail={
                "message": f"Insufficient credits: need {cost} for {reason}, have {balance}",
                "required": cost,
                "balance": balance,
                "reason": reason,
            },
        )
    return {
        "balance": balance,
        "required": cost,
        "reason": reason,
        "user_id": user.id,
        "session_id": session.get("session_id"),
        "azure_cost_usd": action_azure_usd(reason) if reason in COSTS else None,
    }


def require_and_debit(
    db: Session,
    session: dict[str, Any],
    reason: str,
    *,
    ref: str | None = None,
    note: str | None = None,
    amount: int | None = None,
    azure_cost_usd: float | None = None,
    project_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Debit credits for an action. Raises HTTPException 402 if insufficient."""
    cost = amount if amount is not None else cost_for(reason)
    if cost < 0:
        raise ValueError("Debit amount must be non-negative")
    usd = azure_cost_usd if azure_cost_usd is not None else (
        action_azure_usd(reason) if reason in COSTS or reason.startswith("training_") else None
    )
    user = ensure_user_row(db, session)
    balance = int(user.credits_balance or 0)
    if balance < cost:
        raise HTTPException(
            status_code=402,
            detail={
                "message": f"Insufficient credits: need {cost} for {reason}, have {balance}",
                "required": cost,
                "balance": balance,
                "reason": reason,
            },
        )
    if cost == 0:
        event = record_usage_event(
            db,
            user_id=user.id,
            action=reason,
            status="success",
            credits_delta=0,
            azure_cost_usd=usd,
            project_id=project_id,
            ref=ref,
            note=note,
            session_id=session.get("session_id"),
            meta=meta,
        )
        db.commit()
        return {
            "balance": balance,
            "debited": 0,
            "reason": reason,
            "azure_cost_usd": usd,
            "usage_event_id": event.id,
        }
    user.credits_balance = balance - cost
    event = record_usage_event(
        db,
        user_id=user.id,
        action=reason,
        status="success",
        credits_delta=-cost,
        azure_cost_usd=usd,
        project_id=project_id,
        ref=ref,
        note=note,
        session_id=session.get("session_id"),
        meta=meta,
    )
    _append_ledger(
        db,
        user,
        delta=-cost,
        reason=reason,
        ref=ref,
        note=note,
        azure_cost_usd=usd,
        usage_event_id=event.id,
    )
    db.commit()
    db.refresh(user)
    return {
        "balance": int(user.credits_balance),
        "debited": cost,
        "reason": reason,
        "azure_cost_usd": usd,
        "usage_event_id": event.id,
    }


def refund_credits(
    db: Session,
    session: dict[str, Any],
    reason: str,
    *,
    amount: int | None = None,
    ref: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Refund credits after a failed live operation (VLM / AML)."""
    cost = amount if amount is not None else cost_for(reason)
    if cost <= 0:
        user = ensure_user_row(db, session)
        return {"balance": int(user.credits_balance or 0), "refunded": 0, "reason": reason}
    user = ensure_user_row(db, session)
    user.credits_balance = int(user.credits_balance or 0) + cost
    event = record_usage_event(
        db,
        user_id=user.id,
        action=f"refund_{reason}",
        status="refunded",
        credits_delta=cost,
        project_id=None,
        ref=ref,
        note=note or f"Refund for failed {reason}",
        session_id=session.get("session_id"),
    )
    _append_ledger(
        db,
        user,
        delta=cost,
        reason=f"refund_{reason}",
        ref=ref,
        note=note or f"Refund for failed {reason}",
        usage_event_id=event.id,
    )
    db.commit()
    db.refresh(user)
    return {"balance": int(user.credits_balance), "refunded": cost, "reason": reason}


def activate_plan(db: Session, session: dict[str, Any], plan_id: str) -> dict[str, Any]:
    """Activate a plan without payment. Grants package credits once per activation change."""
    plan_id = (plan_id or "").strip().lower()
    if plan_id not in PLANS:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan_id}")
    plan = PLANS[plan_id]
    user = ensure_user_row(db, session)
    current = (user.active_plan or "free").lower()
    if current == plan_id:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Plan '{plan_id}' is already active",
                "balance": int(user.credits_balance or 0),
                "plan": current,
            },
        )
    grant = int(plan["credits"])
    user.active_plan = plan_id
    user.credits_balance = int(user.credits_balance or 0) + grant
    event = record_usage_event(
        db,
        user_id=user.id,
        action="plan_activate",
        status="success",
        credits_delta=grant,
        ref=plan_id,
        note=f"Activated {plan['name']} (+{grant} credits)",
        session_id=session.get("session_id"),
    )
    _append_ledger(
        db,
        user,
        delta=grant,
        reason="plan_activate",
        ref=plan_id,
        note=f"Activated {plan['name']} (+{grant} credits)",
        usage_event_id=event.id,
    )
    db.commit()
    db.refresh(user)
    return {
        "balance": int(user.credits_balance),
        "plan": user.active_plan,
        "granted": grant,
    }


def debit_for_user_id(
    user_id: int,
    reason: str,
    *,
    ref: str | None = None,
    note: str | None = None,
    amount: int | None = None,
    azure_cost_usd: float | None = None,
    project_id: str | None = None,
    session_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Debit in a fresh DB session (for background AML submit / settle threads)."""
    from db.database import get_session_factory

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found for credit debit")
        session = {
            "email": user.email,
            "user_id": user.id,
            "session_id": session_id,
        }
        return require_and_debit(
            db,
            session,
            reason,
            ref=ref,
            note=note,
            amount=amount,
            azure_cost_usd=azure_cost_usd,
            project_id=project_id,
            meta=meta,
        )
    finally:
        db.close()


def refund_debit_for_user_id(
    user_id: int,
    debit_usage_event_id: int,
    session_id: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Idempotently refund a failed inference deploy debit in a fresh DB session."""
    from db.database import get_session_factory

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        debit_event = (
            db.query(UsageEvent)
            .filter(UsageEvent.id == int(debit_usage_event_id))
            .one_or_none()
        )
        if debit_event is None:
            raise ValueError(f"Usage event {debit_usage_event_id} not found")
        if debit_event.user_id != int(user_id):
            raise ValueError("Debit usage event does not belong to the requested user")
        if debit_event.action != "inference_deploy":
            raise ValueError("Usage event is not an inference deployment debit")
        if int(debit_event.credits_delta or 0) >= 0:
            raise ValueError("Inference deployment usage event is not a debit")

        refund_ref = f"usage_event:{debit_event.id}"
        user = (
            db.query(User)
            .filter(User.id == int(user_id))
            .with_for_update()
            .one_or_none()
        )
        if user is None:
            raise HTTPException(status_code=401, detail="User not found for credit refund")

        existing_refund = (
            db.query(UsageEvent)
            .filter(
                UsageEvent.user_id == int(user_id),
                UsageEvent.action == "refund_inference_deploy",
                UsageEvent.ref == refund_ref,
            )
            .one_or_none()
        )
        if existing_refund is not None:
            return {
                "balance": int(user.credits_balance or 0),
                "refunded": 0,
                "original_usage_event_id": debit_event.id,
            }

        amount = -int(debit_event.credits_delta)
        refund_note = note or "Refund for failed inference deployment"
        user.credits_balance = int(user.credits_balance or 0) + amount
        refund_event = record_usage_event(
            db,
            user_id=user.id,
            action="refund_inference_deploy",
            status="refunded",
            credits_delta=amount,
            project_id=debit_event.project_id,
            ref=refund_ref,
            note=refund_note,
            session_id=session_id,
            meta={"original_usage_event_id": debit_event.id},
        )
        _append_ledger(
            db,
            user,
            delta=amount,
            reason="refund_inference_deploy",
            ref=refund_ref,
            note=refund_note,
            usage_event_id=refund_event.id,
        )
        db.commit()
        db.refresh(user)
        return {
            "balance": int(user.credits_balance),
            "refunded": amount,
            "original_usage_event_id": debit_event.id,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def settle_training_compute(
    *,
    user_id: int,
    job_id: str,
    project_id: str,
    duration_seconds: float | None,
    vm_size: str | None,
    job_status: str,
    session_id: int | None = None,
) -> dict[str, Any] | None:
    """Charge Azure VM duration when a training job reaches a terminal state."""
    from db.database import get_session_factory

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Idempotent: skip if we already settled this job.
        existing = (
            db.query(UsageEvent)
            .filter(
                UsageEvent.user_id == int(user_id),
                UsageEvent.action == "training_compute",
                UsageEvent.ref == job_id,
            )
            .one_or_none()
        )
        if existing is not None:
            return None

        credits, usd = training_compute_credits(duration_seconds, vm_size=vm_size)
        note = (
            f"Azure ML {job_status}: {duration_seconds or 0:.0f}s on "
            f"{vm_size or 'configured VM'} ≈ ${usd:.4f}"
        )
        session = {"email": "", "user_id": user_id, "session_id": session_id}
        # ensure_user_row needs email if user_id missing — load user first
        user = db.query(User).filter(User.id == int(user_id)).one_or_none()
        if user is None:
            logger.warning("Training settle skipped: user %s not found", user_id)
            return None
        session["email"] = user.email
        try:
            return require_and_debit(
                db,
                session,
                "training_compute",
                ref=job_id,
                note=note,
                amount=credits,
                azure_cost_usd=usd,
                project_id=project_id,
                meta={
                    "duration_seconds": duration_seconds,
                    "vm_size": vm_size,
                    "job_status": job_status,
                },
            )
        except HTTPException as exc:
            # Still record the usage even if balance goes negative attempt fails —
            # log debt as failed settle; do not silently drop Azure cost.
            if exc.status_code == 402:
                logger.warning(
                    "Insufficient credits to settle training %s for user %s (need %s)",
                    job_id,
                    user_id,
                    credits,
                )
                record_usage_event(
                    db,
                    user_id=user.id,
                    action="training_compute",
                    status="unpaid",
                    credits_delta=0,
                    azure_cost_usd=usd,
                    project_id=project_id,
                    ref=job_id,
                    note=f"UNPAID: {note}",
                    session_id=session_id,
                    meta={
                        "duration_seconds": duration_seconds,
                        "vm_size": vm_size,
                        "job_status": job_status,
                        "required_credits": credits,
                    },
                )
                db.commit()
                return {
                    "balance": int(user.credits_balance or 0),
                    "debited": 0,
                    "reason": "training_compute",
                    "azure_cost_usd": usd,
                    "unpaid": True,
                    "required": credits,
                }
            raise
    finally:
        db.close()


def check_from_request(
    request: Request,
    db: Session,
    reason: str,
    *,
    amount: int | None = None,
) -> dict[str, Any]:
    user = session_user(request)
    return require_balance(db, user, reason, amount=amount)


def debit_from_request(
    request: Request,
    db: Session,
    reason: str,
    *,
    ref: str | None = None,
    note: str | None = None,
    amount: int | None = None,
    azure_cost_usd: float | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    user = session_user(request)
    return require_and_debit(
        db,
        user,
        reason,
        ref=ref,
        note=note,
        amount=amount,
        azure_cost_usd=azure_cost_usd,
        project_id=project_id,
    )


def refund_from_request(
    request: Request,
    db: Session,
    reason: str,
    *,
    ref: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    user = session_user(request)
    return refund_credits(db, user, reason, ref=ref, note=note)
