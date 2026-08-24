from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from dataset_validation import validate_dataset_zip
from db.database import get_db
from schemas.project_spec import ProjectSpec
from services.credits import check_from_request, debit_from_request
from services.project_access import owner_fields, require_project_access, session_user
from services.project_labels import resolve_project_display, should_sync_meta_name
from services.project_store import ProjectStore

router = APIRouter(prefix="/api/projects", tags=["projects"])
store = ProjectStore()
logger = logging.getLogger(__name__)


class CreateProjectBody(BaseModel):
    name: str | None = None


class UpdateSpecBody(BaseModel):
    spec: dict[str, Any]


class ChatBody(BaseModel):
    messages: list[dict[str, Any]]


class DiscoveryPatch(BaseModel):
    ready_for_config: bool | None = None
    detected_task: str | None = None


def _require(meta: dict[str, Any] | None, project_id: str, request: Request) -> dict[str, Any]:
    return require_project_access(meta, project_id, session_user(request))


def _require_task_type(spec: dict[str, Any] | None) -> str:
    """Task type comes from the generated spec — never guessed from the upload."""
    task_type = (spec or {}).get("task_type")
    if not task_type:
        raise HTTPException(
            status_code=400,
            detail="Generate and save the project configuration before uploading a dataset.",
        )
    return str(task_type)


@router.get("")
def list_projects(request: Request):
    user = session_user(request)
    rows = store.list_projects(owner_user_id=user.get("user_id"), owner_email=user["email"])
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        pid = row.get("id")
        if pid:
            meta = store.get_meta(pid)
            if meta:
                spec = store.load_spec(pid)
                labels = resolve_project_display(meta, spec)
                item["display_name"] = labels["display_name"]
                item["subtitle"] = labels["subtitle"]
                item["task_type"] = labels["task_type"]
                better_name = should_sync_meta_name(meta, spec)
                if better_name:
                    meta = store.update_meta(pid, {"name": better_name})
                    item["name"] = better_name
                training = meta.get("training") or {}
                inference = meta.get("inference") or {}
                item["training_status"] = training.get("status")
                item["inference_status"] = inference.get("status") or "not_deployed"
                item["has_model"] = bool(meta.get("model") or training.get("status") == "Completed")
                ds = meta.get("dataset") or {}
                item["dataset_name"] = ds.get("file_name")
        enriched.append(item)
    return {"projects": enriched}


@router.post("")
def create_project(request: Request, body: CreateProjectBody):
    user = session_user(request)
    owners = owner_fields(user)
    meta = store.create(body.name, **owners)
    return {"project": meta}


@router.delete("/{project_id}")
def delete_project(request: Request, project_id: str):
    _require(store.get_meta(project_id), project_id, request)
    store.delete_project(project_id)
    return {"success": True, "deleted": project_id}


@router.get("/{project_id}")
def get_project(request: Request, project_id: str):
    meta = _require(store.get_meta(project_id), project_id, request)
    spec = store.load_spec(project_id)
    chat = store.load_chat(project_id)
    samples = store.list_samples(project_id)
    return {
        "project": meta,
        "spec": spec,
        "chat": chat,
        "samples": [{"id": s, "url": f"/api/projects/{project_id}/samples/{s}"} for s in samples],
    }


@router.patch("/{project_id}/discovery")
def patch_discovery(request: Request, project_id: str, body: DiscoveryPatch):
    _require(store.get_meta(project_id), project_id, request)
    patch: dict[str, Any] = {}
    if body.ready_for_config is not None:
        patch["discovery_ready"] = body.ready_for_config
    if body.detected_task:
        patch["detected_task"] = body.detected_task
    if body.ready_for_config:
        patch["status"] = "discovery_complete"
    return {"project": store.update_meta(project_id, patch)}


@router.put("/{project_id}/spec")
def put_spec(request: Request, project_id: str, body: UpdateSpecBody):
    _require(store.get_meta(project_id), project_id, request)
    spec = store.save_spec(project_id, body.spec)
    return {"spec": spec.model_dump()}


@router.post("/{project_id}/pipeline/tune")
def tune_pipeline(
    request: Request,
    project_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """Analyze random dataset images with VLM and auto-set pipeline fields."""
    _require(store.get_meta(project_id), project_id, request)
    check_from_request(request, db, "pipeline_tune")
    try:
        from services.pipeline_tuning import tune_pipeline_from_dataset

        result = tune_pipeline_from_dataset(project_id, force=force)
        if isinstance(result, dict) and result.get("cached"):
            # Served from the stored tune for this dataset — no VLM call, no charge.
            return result
        credits = debit_from_request(
            request,
            db,
            "pipeline_tune",
            ref=project_id,
            note="Pipeline auto-tune succeeded",
            project_id=project_id,
        )
        if isinstance(result, dict):
            result = {**result, "credits": credits}
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Pipeline tune failed for %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{project_id}/spec")
def get_spec(request: Request, project_id: str):
    _require(store.get_meta(project_id), project_id, request)
    spec = store.load_spec(project_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not generated yet")
    return {"spec": spec}


@router.put("/{project_id}/chat")
def put_chat(request: Request, project_id: str, body: ChatBody):
    _require(store.get_meta(project_id), project_id, request)
    store.save_chat(project_id, body.messages)
    return {"ok": True, "count": len(body.messages)}


@router.get("/{project_id}/chat")
def get_chat(request: Request, project_id: str):
    _require(store.get_meta(project_id), project_id, request)
    return {"messages": store.load_chat(project_id)}


@router.post("/{project_id}/samples")
async def upload_sample(request: Request, project_id: str, file: UploadFile = File(...)):
    _require(store.get_meta(project_id), project_id, request)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are allowed")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 15 MB")
    name = file.filename or "sample.jpg"
    item = store.add_sample(project_id, name, data, file.content_type)
    # Only include inline preview for small images (UI can use item.url otherwise).
    if len(data) <= 250_000:
        b64 = base64.b64encode(data).decode("ascii")
        item["data_url"] = f"data:{file.content_type};base64,{b64}"
    return item


@router.get("/{project_id}/samples/{sample_id}")
def get_sample(request: Request, project_id: str, sample_id: str):
    _require(store.get_meta(project_id), project_id, request)
    result = store.read_sample(project_id, sample_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    data, ctype = result
    return Response(content=data, media_type=ctype)


@router.get("/{project_id}/dataset/file")
def download_dataset_file(request: Request, project_id: str):
    """Download raw dataset ZIP (local storage or proxied for training debug)."""
    _require(store.get_meta(project_id), project_id, request)
    data = store.read_dataset(project_id)
    if not data:
        raise HTTPException(status_code=404, detail="No dataset uploaded")
    meta = store.get_meta(project_id) or {}
    fname = (meta.get("dataset") or {}).get("file_name") or "dataset.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/{project_id}/dataset/class/{class_name}/images")
async def upload_classification_images(
    request: Request,
    project_id: str,
    class_name: str,
    files: list[UploadFile] = File(...),
):
    meta = _require(store.get_meta(project_id), project_id, request)
    spec = store.load_spec(project_id)
    expected = spec.get("classes") if spec else None
    if expected:
        normalized = {c.lower(): c for c in expected}
        if class_name.lower() not in normalized:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown class '{class_name}'. Expected: {', '.join(expected)}",
            )
        class_name = normalized[class_name.lower()]

    batch: list[tuple[str, bytes, str]] = []
    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image uploads are allowed")
        data = await file.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Each image must be under 15 MB")
        batch.append((file.filename or "image.jpg", data, file.content_type))

    if not batch:
        raise HTTPException(status_code=400, detail="No valid images in upload")

    result = store.add_classification_images(project_id, class_name, batch)
    updated = store.get_meta(project_id) or meta
    return {"project": updated, **result}


@router.get("/{project_id}/dataset/classification")
def get_classification_dataset(request: Request, project_id: str):
    _require(store.get_meta(project_id), project_id, request)
    status = store.get_classification_status(project_id)
    return status


@router.delete("/{project_id}/dataset/class/{class_name}")
def clear_classification_class(request: Request, project_id: str, class_name: str):
    _require(store.get_meta(project_id), project_id, request)
    status = store.clear_classification_class(project_id, class_name)
    store.revalidate_classification(project_id)
    return {"success": True, **status}


@router.post("/{project_id}/dataset/classification/validate")
def revalidate_classification_dataset(request: Request, project_id: str):
    _require(store.get_meta(project_id), project_id, request)
    status = store.revalidate_classification(project_id)
    return {"project": store.get_meta(project_id), "validation": status["validation"]}


@router.get("/{project_id}/dataset/status")
def get_dataset_status(request: Request, project_id: str):
    _require(store.get_meta(project_id), project_id, request)
    return store.get_dataset_status(project_id)


@router.post("/{project_id}/dataset/multi-label/images")
async def upload_multi_label_images(
    request: Request,
    project_id: str,
    files: list[UploadFile] = File(...),
):
    meta = _require(store.get_meta(project_id), project_id, request)
    batch: list[tuple[str, bytes, str]] = []
    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image uploads are allowed")
        data = await file.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Each image must be under 15 MB")
        batch.append((file.filename or "image.jpg", data, file.content_type))
    if not batch:
        raise HTTPException(status_code=400, detail="No valid images in upload")
    result = store.add_multi_label_images(project_id, batch)
    return {"project": store.get_meta(project_id) or meta, **result}


@router.post("/{project_id}/dataset/multi-label/manifest")
async def upload_multi_label_manifest(
    request: Request,
    project_id: str,
    file: UploadFile = File(...),
):
    meta = _require(store.get_meta(project_id), project_id, request)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Manifest file required")
    lower = file.filename.lower()
    if not (lower.endswith(".csv") or lower.endswith(".json")):
        raise HTTPException(status_code=400, detail="Upload a CSV or JSON label manifest")
    data = await file.read()
    result = store.save_multi_label_manifest(project_id, file.filename, data)
    return {"project": store.get_meta(project_id) or meta, **result}


@router.post("/{project_id}/dataset/regression/images")
async def upload_regression_images(
    request: Request,
    project_id: str,
    files: list[UploadFile] = File(...),
):
    meta = _require(store.get_meta(project_id), project_id, request)
    batch: list[tuple[str, bytes, str]] = []
    for file in files:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image uploads are allowed")
        data = await file.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Each image must be under 15 MB")
        batch.append((file.filename or "image.jpg", data, file.content_type))
    if not batch:
        raise HTTPException(status_code=400, detail="No valid images in upload")
    result = store.add_regression_images(project_id, batch)
    return {"project": store.get_meta(project_id) or meta, **result}


@router.post("/{project_id}/dataset/regression/targets")
async def upload_regression_targets(
    request: Request,
    project_id: str,
    file: UploadFile = File(...),
):
    meta = _require(store.get_meta(project_id), project_id, request)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV with image,target columns")
    data = await file.read()
    result = store.save_regression_targets(project_id, file.filename, data)
    return {"project": store.get_meta(project_id) or meta, **result}


@router.post("/{project_id}/dataset/annotated")
async def upload_annotated_dataset(
    request: Request,
    project_id: str,
    file: UploadFile = File(...),
):
    meta = _require(store.get_meta(project_id), project_id, request)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip annotated dataset archive")
    data = await file.read()
    spec = store.load_spec(project_id)
    task_type = _require_task_type(spec)
    result = store.save_annotated_dataset(project_id, file.filename, data, task_type)
    updated = store.get_meta(project_id) or meta
    return {"project": updated, **result}


@router.post("/{project_id}/dataset")
async def upload_dataset(request: Request, project_id: str, file: UploadFile = File(...)):
    """Legacy ZIP upload — routes to annotated or class-folder validation by task type."""
    meta = _require(store.get_meta(project_id), project_id, request)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip dataset archive")
    data = await file.read()
    spec = store.load_spec(project_id)
    task_type = _require_task_type(spec)

    if task_type in ("object_detection", "object_localization"):
        result = store.save_annotated_dataset(project_id, file.filename, data, task_type)
        updated = store.get_meta(project_id) or meta
        return {"project": updated, **result}

    if task_type == "classification":
        dataset = store.save_dataset(project_id, file.filename, data)
        expected = spec.get("classes") if spec else None
        validation = validate_dataset_zip(data, expected)
        store.mark_dataset_validated(project_id, validation)
        updated = store.get_meta(project_id) or meta
        return {"project": updated, "dataset": dataset, "validation": validation}

    raise HTTPException(
        status_code=400,
        detail=f"Task type '{task_type}' uses dedicated upload endpoints (images + manifest/CSV).",
    )


@router.post("/{project_id}/dataset/validate")
def revalidate_dataset(request: Request, project_id: str):
    meta = _require(store.get_meta(project_id), project_id, request)
    data = store.read_dataset(project_id)
    if not data:
        raise HTTPException(status_code=400, detail="No dataset uploaded")
    spec = store.load_spec(project_id)
    expected = spec.get("classes") if spec else None
    validation = validate_dataset_zip(data, expected)
    store.mark_dataset_validated(project_id, validation)
    return {"project": store.get_meta(project_id), "validation": validation}


@router.post("/{project_id}/complete-setup")
def complete_setup(request: Request, project_id: str):
    """Mark project ready for training (training job itself is a later phase)."""
    meta = _require(store.get_meta(project_id), project_id, request)
    spec = store.load_spec(project_id)
    if not spec:
        raise HTTPException(status_code=400, detail="Generate and save configuration first")
    ds = meta.get("dataset") or {}
    task_type = _require_task_type(spec)

    if task_type == "classification" or ds.get("mode") == "classification":
        status = store.get_classification_status(project_id)
        if not status.get("validated"):
            errors = (status.get("validation") or {}).get("errors") or []
            raise HTTPException(
                status_code=400,
                detail=errors[0] if errors else "Upload and validate classification images first",
            )
    else:
        status = store.get_dataset_status(project_id)
        if not status.get("validated"):
            errors = (status.get("validation") or {}).get("errors") or []
            raise HTTPException(
                status_code=400,
                detail=errors[0] if errors else "Upload and validate dataset first",
            )
    return {
        "project": store.update_meta(project_id, {"status": "ready_for_training"}),
        "message": "Setup complete. You can start training from the next step.",
    }
