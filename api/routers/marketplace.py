"""Marketplace catalog API — browse datasets/models and import into projects."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from schemas.marketplace import (
    MARKETPLACE_INDUSTRIES,
    MarketplaceImportBody,
    SUPPORTED_TASK_TYPES,
)
from services.marketplace_import import _model_display_name, get_marketplace_import_service
from services.marketplace_store import get_marketplace_store
from services.project_access import owner_fields, require_project_access, session_user
from services.project_store import ProjectStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketplace"])
store = ProjectStore()
marketplace = get_marketplace_store()
importer = get_marketplace_import_service()


def _dataset_dict(item: Any) -> dict[str, Any]:
    return item.model_dump()


def _model_dict(item: Any) -> dict[str, Any]:
    return item.model_dump()


@router.get("/api/marketplace/datasets")
def list_marketplace_datasets(
    task_type: str | None = Query(None),
    industry: str | None = Query(None),
):
    if task_type and task_type not in SUPPORTED_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported task_type. Use one of: {SUPPORTED_TASK_TYPES}")
    if industry and industry not in MARKETPLACE_INDUSTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported industry. Use one of: {MARKETPLACE_INDUSTRIES}",
        )
    items = marketplace.list_datasets(task_type, industry)
    return {
        "datasets": [_dataset_dict(d) for d in items],
        "task_types": list(SUPPORTED_TASK_TYPES),
        "industries": list(MARKETPLACE_INDUSTRIES),
    }


@router.get("/api/marketplace/models")
def list_marketplace_models(
    task_type: str | None = Query(None),
    industry: str | None = Query(None),
):
    if task_type and task_type not in SUPPORTED_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported task_type. Use one of: {SUPPORTED_TASK_TYPES}")
    if industry and industry not in MARKETPLACE_INDUSTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported industry. Use one of: {MARKETPLACE_INDUSTRIES}",
        )
    items = marketplace.list_models(task_type, industry)
    return {
        "models": [_model_dict(m) for m in items],
        "task_types": list(SUPPORTED_TASK_TYPES),
        "industries": list(MARKETPLACE_INDUSTRIES),
    }

@router.get("/api/marketplace/datasets/{item_id}")
def get_marketplace_dataset(item_id: str):
    item = marketplace.get_dataset(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset not found in marketplace catalog")
    return {"dataset": _dataset_dict(item)}


@router.get("/api/marketplace/models/{item_id}")
def get_marketplace_model(item_id: str):
    item = marketplace.get_model(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model not found in marketplace catalog")
    return {"model": _model_dict(item)}


@router.get("/api/marketplace/datasets/{item_id}/previews")
def get_marketplace_dataset_previews(item_id: str):
    payload = marketplace.get_dataset_preview_payload(item_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Dataset not found in marketplace catalog")
    return payload


@router.get("/api/marketplace/datasets/{item_id}/previews/{filename}")
def get_marketplace_dataset_preview_image(item_id: str, filename: str):
    result = marketplace.read_dataset_preview(item_id, filename)
    if result is None:
        raise HTTPException(status_code=404, detail="Preview image not found")
    data, content_type = result
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/api/marketplace/models/{item_id}/previews")
def get_marketplace_model_previews(item_id: str):
    payload = marketplace.get_model_preview_payload(item_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Model not found in marketplace catalog")
    return payload


@router.post("/api/marketplace/models/{item_id}/start-project")
def start_project_from_model(request: Request, item_id: str):
    item = marketplace.get_model(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model not found in marketplace catalog")
    try:
        user = session_user(request)
        meta = store.create(_model_display_name(item), **owner_fields(user))
        project_id = meta["id"]
        payload = importer.bootstrap_project_from_model(project_id, item_id)
        payload["project_id"] = project_id
        return payload
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/marketplace/datasets/{item_id}/start-project")
def start_project_from_dataset(request: Request, item_id: str):
    item = marketplace.get_dataset(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset not found in marketplace catalog")
    try:
        user = session_user(request)
        meta = store.create(item.name, **owner_fields(user))
        project_id = meta["id"]
        payload = importer.link_dataset_from_marketplace(project_id, item_id)
        payload["project_id"] = project_id
        return payload
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/dataset/import-marketplace")
def import_marketplace_dataset(request: Request, project_id: str, body: MarketplaceImportBody):
    require_project_access(store.get_meta(project_id), project_id, session_user(request))
    try:
        payload = importer.link_dataset_from_marketplace(project_id, body.item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return payload


@router.post("/api/projects/{project_id}/model/import-marketplace")
def import_marketplace_model(request: Request, project_id: str, body: MarketplaceImportBody):
    require_project_access(store.get_meta(project_id), project_id, session_user(request))
    try:
        result = importer.import_model(project_id, body.item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    meta = store.get_meta(project_id)
    return {"project": meta, **result}
