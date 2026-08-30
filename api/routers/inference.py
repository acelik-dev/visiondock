"""Inference deployment — Azure ML endpoints, API keys, edge bundles."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from db.database import get_db
from services.azure_pricing import configured_inference_vm, inference_deploy_credits
from services.credits import check_from_request, debit_from_request
from services.project_access import require_project_access, session_user
from services.inference_service import get_inference_service
from services.project_store import ProjectStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/inference", tags=["inference"])
_store = ProjectStore()


def _require_project(request: Request, project_id: str) -> dict[str, Any]:
    return require_project_access(_store.get_meta(project_id), project_id, session_user(request))


@router.get("/{project_id}")
def get_inference_status(request: Request, project_id: str):
    _require_project(request, project_id)
    svc = get_inference_service()
    inference = svc.deploy_status(project_id)
    meta = _store.get_meta(project_id) or {}
    training = meta.get("training") or {}
    model = meta.get("model") or {}
    return {
        "project_id": project_id,
        "project_status": meta.get("status"),
        "training_status": training.get("status"),
        "training_job_id": training.get("job_id"),
        "inference": inference,
        "model": model,
        "can_deploy": training.get("status") == "Completed" or bool(model.get("weights_blob")),
    }


@router.post("/{project_id}/deploy")
def deploy_inference(request: Request, project_id: str, db: Session = Depends(get_db)):
    meta = _require_project(request, project_id)
    training = meta.get("training") or {}
    job_id = training.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="No completed training job for this project")
    if training.get("status") != "Completed":
        raise HTTPException(status_code=400, detail="Training must be completed before deploy")

    svc = get_inference_service()
    model_bytes = svc.model_size_bytes(project_id, str(job_id))
    vm_size = configured_inference_vm()
    amount, usd = inference_deploy_credits(model_bytes=model_bytes, vm_size=vm_size)
    balance_check = check_from_request(request, db, "inference_deploy", amount=amount)

    svc.ensure_api_key(project_id)
    credits: dict[str, Any] | None = None
    size_note = f"{(model_bytes or 0) / (1024 * 1024):.1f} MB model" if model_bytes else "model"

    def _bill_deployment() -> dict[str, Any]:
        nonlocal credits
        credits = debit_from_request(
            request,
            db,
            "inference_deploy",
            ref=project_id,
            note=f"Endpoint provisioning on {vm_size} ({size_note}) ≈ ${usd:.4f}",
            amount=amount,
            azure_cost_usd=usd,
            project_id=project_id,
        )
        return {
            "user_id": int(balance_check["user_id"]),
            "session_id": balance_check.get("session_id"),
            "debit_usage_event_id": int(credits["usage_event_id"]),
        }

    started = svc.register_and_deploy(
        project_id,
        str(job_id),
        billing_factory=_bill_deployment,
    )
    if not started:
        # Already provisioning — the in-flight deploy was the one that got charged.
        return {
            "success": True,
            "message": "Inference deployment already in progress",
            "inference": svc.deploy_status(project_id),
            "credits": None,
        }

    return {
        "success": True,
        "message": "Inference deployment started on Azure ML",
        "inference": svc.deploy_status(project_id),
        "credits": credits,
    }


@router.post("/{project_id}/api-key")
def rotate_api_key(request: Request, project_id: str):
    _require_project(request, project_id)
    key = get_inference_service().ensure_api_key(project_id, rotate=True)
    inference = get_inference_service().get_inference_meta(project_id)
    return {
        "success": True,
        "api_key": key,
        "inference": inference,
    }


@router.post("/{project_id}/predict")
async def predict_inference(
    project_id: str,
    request: Request,
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Proxy image inference to the deployed Azure ML scoring endpoint."""
    meta = _require_project(request, project_id)
    check_from_request(request, db, "inference_predict")
    inference = meta.get("inference") or {}
    if inference.get("status") != "deployed":
        raise HTTPException(status_code=400, detail="Inference endpoint not deployed")

    scoring_uri = inference.get("scoring_uri")
    aml_key = inference.get("aml_primary_key")
    if not scoring_uri or not aml_key:
        raise HTTPException(
            status_code=400,
            detail="Missing scoring_uri or aml_primary_key — redeploy inference",
        )

    model_meta = meta.get("model") or {}
    conf = float(inference.get("confidence_threshold", 0.5))
    iou = float(inference.get("nms_iou_threshold", 0.5))
    tta = bool(inference.get("tta", False))
    ensemble = bool(inference.get("ensemble", False))
    sahi = bool(inference.get("sahi", False))
    sahi_slice = int(inference.get("sahi_slice_size", 640))
    sahi_overlap = float(inference.get("sahi_overlap_ratio", 0.2))
    task_type = str(
        inference.get("task_type") or model_meta.get("task_type") or "classification"
    )
    if task_type in ("object_detection", "object_localization"):
        task_type = "object_detection"
    image_b64: str | None = None
    top_k = 5
    threshold = conf

    if file and file.filename:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty image file")
        image_b64 = base64.b64encode(raw).decode("ascii")
    else:
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="JSON body must be an object")
            image_b64 = body.get("image_base64")
            if "confidence" in body:
                conf = float(body["confidence"])
                threshold = conf
            if "threshold" in body:
                threshold = float(body["threshold"])
            if "top_k" in body:
                top_k = int(body["top_k"])
            if "iou" in body:
                iou = float(body["iou"])
            if "nms_iou_threshold" in body:
                iou = float(body["nms_iou_threshold"])
            if "tta" in body:
                tta = bool(body["tta"])
            if "ensemble" in body:
                ensemble = bool(body["ensemble"])
            if "sahi" in body:
                sahi = bool(body["sahi"])

    if not image_b64:
        raise HTTPException(
            status_code=400,
            detail="Provide multipart file or JSON with image_base64",
        )

    if task_type == "classification":
        payload = {
            "image_base64": image_b64,
            "top_k": top_k,
            "confidence": conf,
            "confidence_threshold": conf,
        }
    elif task_type == "multi_label":
        payload = {"image_base64": image_b64, "confidence": threshold}
    elif task_type == "regression":
        payload = {"image_base64": image_b64}
    else:
        payload = {
            "image_base64": image_b64,
            "confidence": conf,
            "iou": iou,
            "nms_iou_threshold": iou,
            "tta": tta,
            "ensemble": ensemble,
            "sahi": sahi,
            "sahi_slice_size": sahi_slice,
            "sahi_overlap_ratio": sahi_overlap,
        }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                scoring_uri,
                json=payload,
                headers={
                    "Authorization": f"Bearer {aml_key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        logger.exception("AML predict request failed for %s", project_id)
        raise HTTPException(status_code=502, detail=f"AML request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=resp.text[:500] or "AML scoring failed",
        )

    try:
        result = resp.json()
    except json.JSONDecodeError:
        result = {"raw": resp.text}

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"raw": result}

    credits = debit_from_request(
        request,
        db,
        "inference_predict",
        ref=project_id,
        note="Inference predict succeeded",
    )

    if isinstance(result, dict):
        result = {**result, "credits": credits}
        return result
    return {"result": result, "credits": credits}


@router.get("/{project_id}/edge-bundle")
def download_edge_bundle(request: Request, project_id: str):
    _require_project(request, project_id)
    try:
        data = get_inference_service().build_edge_bundle(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="visiondock-edge-{project_id}.zip"'
        },
    )
