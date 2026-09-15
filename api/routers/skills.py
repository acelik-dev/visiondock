"""Skills catalog API — public list + admin CRUD."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from schemas.skills import SkillUpsertBody
from services.admin_access import require_admin
from services.skill_registry import list_entrypoints
from services.skills_store import get_skills_store

router = APIRouter(tags=["skills"])
store = get_skills_store()


@router.get("/api/skills")
def list_skills(
    task_type: str | None = Query(None),
    enabled_only: bool = Query(True),
):
    store.ensure_seeded()
    items = store.list_skills(enabled_only=enabled_only, task_type=task_type)
    return {
        "skills": [s.model_dump() for s in items],
        "updated_at": store.get_catalog().updated_at,
    }


@router.get("/api/skills/entrypoints")
def list_skill_entrypoints(stage: str | None = Query(None)):
    # Entrypoints are needed by admin UI; allow any authenticated session via middleware.
    return {"entrypoints": list_entrypoints(stage=stage)}


@router.get("/api/admin/skills")
def admin_list_skills(request: Request):
    require_admin(request)
    store.ensure_seeded()
    catalog = store.get_catalog(refresh=True)
    return {
        "skills": [s.model_dump() for s in catalog.skills],
        "updated_at": catalog.updated_at,
        "is_admin": True,
    }


@router.post("/api/admin/skills")
def admin_create_skill(request: Request, body: SkillUpsertBody):
    require_admin(request)
    try:
        item = store.upsert_skill(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"skill": item.model_dump()}


@router.put("/api/admin/skills/{skill_id}")
def admin_update_skill(skill_id: str, request: Request, body: SkillUpsertBody):
    require_admin(request)
    try:
        item = store.upsert_skill(body, skill_id=skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"skill": item.model_dump()}


@router.delete("/api/admin/skills/{skill_id}")
def admin_delete_skill(skill_id: str, request: Request):
    require_admin(request)
    if not store.delete_skill(skill_id):
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"ok": True, "id": skill_id}


@router.post("/api/admin/skills/reseed")
def admin_reseed_skills(request: Request):
    """Replace catalog with built-in seed (destructive)."""
    require_admin(request)
    from services.skills_store import SkillsCatalog, SkillItem, default_seed_skills, _now

    catalog = SkillsCatalog(
        version="1",
        updated_at=_now(),
        skills=[SkillItem.model_validate(s) for s in default_seed_skills()],
    )
    store.save_catalog(catalog)
    return {"ok": True, "count": len(catalog.skills), "updated_at": catalog.updated_at}
