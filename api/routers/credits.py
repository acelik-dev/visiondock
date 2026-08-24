"""Credits and plan activation (no payment)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from services.azure_pricing import pricing_catalog
from services.credits import PLANS, activate_plan, get_account
from services.project_access import session_user

router = APIRouter(prefix="/api/credits", tags=["credits"])


class ActivatePlanRequest(BaseModel):
    plan: str = Field(..., description="free | starter | pro")


@router.get("/me")
def credits_me(request: Request, db: Session = Depends(get_db)):
    session = session_user(request)
    return {"success": True, "data": get_account(db, session)}


@router.get("/costs")
def credits_costs(request: Request):
    session_user(request)
    catalog = pricing_catalog()
    return {
        "success": True,
        "data": {
            "costs": catalog["costs"],
            "plans": list(PLANS.values()),
            "pricing": {
                "credit_usd": catalog["credit_usd"],
                "platform_markup": catalog["platform_markup"],
                "region_note": catalog["region_note"],
                "vm_size": catalog["vm_size"],
                "vm_hourly_usd": catalog["vm_hourly_usd"],
                "training_billing": catalog["training_billing"],
                "cost_notes": catalog["cost_notes"],
                "azure_rates": catalog["azure_rates"],
            },
        },
    }


@router.post("/activate-plan")
def credits_activate_plan(
    body: ActivatePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = session_user(request)
    result = activate_plan(db, session, body.plan)
    return {"success": True, "data": result}
