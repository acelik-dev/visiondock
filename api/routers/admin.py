"""Admin console APIs — overview, users, credits, projects, marketplace, system."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import CreditLedger, User, UserSession
from services.admin_access import admin_emails, require_admin
from services.credits import admin_adjust_credits, admin_set_user_plan, get_plans
from services.billing_config import get_billing_config, save_billing_config
from services.marketplace_store import get_marketplace_store
from services.project_store import ProjectStore
from services.skills_store import get_skills_store
from storage.blob_store import get_blob_store

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdjustCreditsBody(BaseModel):
    delta: int = Field(..., description="Positive to grant, negative to revoke")
    note: str | None = Field(None, max_length=500)


class SetPlanBody(BaseModel):
    plan_id: str
    grant_credits: bool = True


class BillingConfigBody(BaseModel):
    credit_usd: float | None = None
    platform_markup: float | None = None
    action_credits: dict[str, int] | None = None
    plans: dict[str, dict[str, Any]] | None = None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.get("/overview")
def admin_overview(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    user_count = db.query(func.count(User.id)).scalar() or 0
    credit_sum = db.query(func.coalesce(func.sum(User.credits_balance), 0)).scalar() or 0
    active_sessions = (
        db.query(func.count(UserSession.id))
        .filter(UserSession.revoked_at.is_(None))
        .scalar()
        or 0
    )

    projects = ProjectStore().list_projects()
    by_status: dict[str, int] = {}
    training = 0
    deployed = 0
    for p in projects:
        st = str(p.get("status") or p.get("training_status") or "unknown").lower()
        key = st.split()[0] if st else "unknown"
        by_status[key] = by_status.get(key, 0) + 1
        ts = str(p.get("training_status") or "").lower()
        if "train" in ts or "running" in ts or "queued" in ts:
            training += 1
        if str(p.get("inference_status") or "").lower() == "deployed" or p.get("has_model"):
            deployed += 1

    mstore = get_marketplace_store()
    catalog = mstore.get_catalog()
    skills = get_skills_store()
    skills.ensure_seeded()
    skill_items = skills.list_skills(enabled_only=False)

    return {
        "users": int(user_count),
        "credits_in_circulation": int(credit_sum),
        "active_sessions": int(active_sessions),
        "projects": len(projects),
        "projects_training": training,
        "projects_with_models": deployed,
        "project_status_counts": by_status,
        "marketplace_datasets": len(catalog.datasets),
        "marketplace_models": len(catalog.models),
        "skills_total": len(skill_items),
        "skills_enabled": sum(1 for s in skill_items if s.enabled),
        "plans": list(get_plans().values()),
        "admin_email_count": len(admin_emails()),
    }


@router.get("/users")
def admin_list_users(
    request: Request,
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Filter by email or name"),
    limit: int = Query(100, ge=1, le=500),
):
    require_admin(request)
    query = db.query(User).order_by(User.created_at.desc())
    if q and q.strip():
        needle = f"%{q.strip().lower()}%"
        query = query.filter(
            (func.lower(User.email).like(needle)) | (func.lower(User.name).like(needle))
        )
    rows = query.limit(limit).all()
    allowed = admin_emails()
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "credits_balance": int(u.credits_balance or 0),
                "active_plan": u.active_plan or "free",
                "email_verified": bool(u.email_verified_at),
                "is_admin": (u.email or "").strip().lower() in allowed,
                "created_at": _iso(u.created_at),
                "last_login": _iso(u.last_login),
            }
            for u in rows
        ],
        "count": len(rows),
    }


@router.post("/users/{user_id}/credits")
def admin_user_credits(
    user_id: int,
    body: AdjustCreditsBody,
    request: Request,
    db: Session = Depends(get_db),
):
    admin = require_admin(request)
    return {
        "success": True,
        "data": admin_adjust_credits(
            db,
            user_id=user_id,
            delta=body.delta,
            note=body.note,
            admin_email=admin,
        ),
    }


@router.get("/users/{user_id}/ledger")
def admin_user_ledger(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    require_admin(request)
    user = db.query(User).filter(User.id == int(user_id)).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    rows = (
        db.query(CreditLedger)
        .filter(CreditLedger.user_id == user.id)
        .order_by(CreditLedger.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "user_id": user.id,
        "email": user.email,
        "balance": int(user.credits_balance or 0),
        "ledger": [
            {
                "id": r.id,
                "delta": r.delta,
                "balance_after": r.balance_after,
                "reason": r.reason,
                "ref": r.ref,
                "note": r.note,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ],
    }


@router.post("/users/{user_id}/plan")
def admin_user_plan(
    user_id: int,
    body: SetPlanBody,
    request: Request,
    db: Session = Depends(get_db),
):
    admin = require_admin(request)
    return {
        "success": True,
        "data": admin_set_user_plan(
            db,
            user_id=user_id,
            plan_id=body.plan_id.strip().lower(),
            grant_credits=body.grant_credits,
            admin_email=admin,
        ),
    }


@router.get("/ledger")
def admin_global_ledger(
    request: Request,
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Filter by email, reason, or note"),
    limit: int = Query(100, ge=1, le=500),
):
    require_admin(request)
    query = (
        db.query(CreditLedger, User)
        .join(User, User.id == CreditLedger.user_id)
        .order_by(CreditLedger.created_at.desc())
    )
    if q and q.strip():
        needle = f"%{q.strip().lower()}%"
        query = query.filter(
            (func.lower(User.email).like(needle))
            | (func.lower(CreditLedger.reason).like(needle))
            | (func.lower(func.coalesce(CreditLedger.note, "")).like(needle))
        )
    rows = query.limit(limit).all()
    return {
        "count": len(rows),
        "entries": [
            {
                "id": ledger.id,
                "user_id": user.id,
                "email": user.email,
                "delta": ledger.delta,
                "balance_after": ledger.balance_after,
                "reason": ledger.reason,
                "ref": ledger.ref,
                "note": ledger.note,
                "created_at": _iso(ledger.created_at),
            }
            for ledger, user in rows
        ],
    }


@router.get("/billing")
def admin_get_billing(request: Request):
    require_admin(request)
    return get_billing_config(refresh=True)


@router.put("/billing")
def admin_put_billing(body: BillingConfigBody, request: Request):
    require_admin(request)
    patch = body.model_dump(exclude_unset=True)
    return save_billing_config(patch)


@router.get("/projects")
def admin_list_projects(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
):
    require_admin(request)
    store = ProjectStore()
    rows = store.list_projects()[:limit]
    enriched: list[dict[str, Any]] = []
    for row in rows:
        pid = row.get("id")
        meta = store.get_meta(pid) if pid else None
        meta = meta or {}
        enriched.append(
            {
                "id": pid,
                "name": meta.get("name") or row.get("name") or pid,
                "status": meta.get("status") or row.get("status"),
                "training_status": meta.get("training_status") or row.get("training_status"),
                "inference_status": meta.get("inference_status") or row.get("inference_status"),
                "owner_email": meta.get("owner_email") or row.get("owner_email"),
                "owner_user_id": meta.get("owner_user_id") or row.get("owner_user_id"),
                "updated_at": meta.get("updated_at") or row.get("updated_at"),
                "created_at": meta.get("created_at") or row.get("created_at"),
                "detected_task": meta.get("detected_task") or row.get("detected_task"),
                "has_dataset": bool((meta.get("dataset") or {}).get("uploaded") or (meta.get("dataset") or {}).get("validated")),
                "marketplace_dataset": (meta.get("dataset") or {}).get("marketplace_name"),
            }
        )
    return {"projects": enriched, "count": len(enriched)}


@router.get("/marketplace")
def admin_marketplace(request: Request):
    require_admin(request)
    catalog = get_marketplace_store().get_catalog(refresh=True)
    by_industry: dict[str, int] = {}
    by_task: dict[str, int] = {}
    for d in catalog.datasets:
        by_task[d.task_type] = by_task.get(d.task_type, 0) + 1
        for ind in d.industries or []:
            by_industry[ind] = by_industry.get(ind, 0) + 1
    return {
        "updated_at": catalog.updated_at,
        "version": catalog.version,
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "task_type": d.task_type,
                "image_count": d.image_count,
                "industries": d.industries,
                "license": d.license,
                "size_label": d.size_label,
            }
            for d in catalog.datasets
        ],
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "task_type": m.task_type,
                "architecture": m.architecture,
                "industries": m.industries,
            }
            for m in catalog.models
        ],
        "dataset_count": len(catalog.datasets),
        "model_count": len(catalog.models),
        "by_industry": by_industry,
        "by_task": by_task,
    }


@router.get("/system")
def admin_system(request: Request):
    require_admin(request)
    store = get_blob_store()
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    skills = get_skills_store()
    skills.ensure_seeded()
    catalog = skills.get_catalog()
    return {
        "storage_backend": backend,
        "storage_container": os.getenv("AZURE_STORAGE_CONTAINER", "visiondock"),
        "admin_emails": sorted(admin_emails()),
        "auth_username_fallback": bool(
            (os.getenv("AUTH_USERNAME") or os.getenv("BASIC_AUTH_USERNAME") or "").strip()
        ),
        "azure_ml_workspace": os.getenv("AZURE_ML_WORKSPACE") or None,
        "azure_resource_group": os.getenv("AZURE_RESOURCE_GROUP") or None,
        "public_api_url": os.getenv("PUBLIC_API_URL") or None,
        "skills_catalog_updated_at": catalog.updated_at,
        "skills_version": catalog.version,
        "blob_reachable": True,
        "blob_store_type": type(store).__name__,
    }
