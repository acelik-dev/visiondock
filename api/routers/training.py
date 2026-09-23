"""Training API router for Azure ML integration."""
import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.azure_pricing import configured_vm_size, vm_hourly_usd
from services.credits import (
    check_from_request,
    cost_for,
    ensure_user_row,
    settle_training_compute,
)
from services.project_access import require_project_access, session_user
from services.project_store import ProjectStore
from services.pipeline_env import merge_spec_pipeline_into_config, pipeline_env_from_spec
from services.training_submit_queue import (
    clear_submission_result,
    get_submission_error,
    is_inflight,
    peek_error,
    peek_submission_result,
    start_submission,
)
from services.user_sessions import record_usage_event
from db.database import get_session_factory

# Import Azure ML service (with fallback for local dev)
AZURE_ML_IMPORT_ERROR: str | None = None
AZURE_ML_AVAILABLE = False
try:
    from services.azure_ml_service import get_ml_service, normalize_training_metrics

    AZURE_ML_AVAILABLE = True
except Exception as e:
    AZURE_ML_IMPORT_ERROR = str(e)
    logging.warning(f"Azure ML SDK not available: {e}. Using mock mode.")

    def normalize_training_metrics(raw: dict[str, Any]) -> dict[str, Any]:
        return raw or {}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/training", tags=["training"])
_project_store = ProjectStore()

# Azure ML VM size → display labels (West Europe NCas T4 cluster)
_VM_GPU_PROFILES: dict[str, dict[str, Any]] = {
    "Standard_NC4as_T4_v3": {"gpu": "NVIDIA T4", "vram_gb": 16},
    "Standard_NC8as_T4_v3": {"gpu": "NVIDIA T4", "vram_gb": 16},
    "Standard_NC16as_T4_v3": {"gpu": "NVIDIA T4", "vram_gb": 16},
    "Standard_NC6s_v3": {"gpu": "NVIDIA V100", "vram_gb": 16},
    "Standard_NC12s_v3": {"gpu": "NVIDIA V100", "vram_gb": 16},
    "Standard_NC24rs_v3": {"gpu": "NVIDIA V100", "vram_gb": 16},
    "Standard_ND96asr_v4": {"gpu": "NVIDIA A100", "vram_gb": 80},
}

# Rough $/hour for duration/cost estimates (from azure_pricing Sweden Central rates)
_VM_HOURLY_USD: dict[str, float] = {
    "Standard_NC4as_T4_v3": vm_hourly_usd("Standard_NC4as_T4_v3"),
    "Standard_NC8as_T4_v3": vm_hourly_usd("Standard_NC8as_T4_v3"),
    "Standard_NC16as_T4_v3": vm_hourly_usd("Standard_NC16as_T4_v3"),
    "Standard_D4s_v3": vm_hourly_usd("Standard_D4s_v3"),
}


def _estimate_training(epochs: int, vm_size: str) -> dict[str, Any]:
    minutes_per_epoch = 4.0 if epochs >= 50 else 2.5
    total_minutes = max(int(epochs * minutes_per_epoch), 15)
    hours = total_minutes / 60.0
    # VM rate + workspace/storage overhead (typical VisionDock job)
    vm_rate = _VM_HOURLY_USD.get(vm_size, vm_hourly_usd(vm_size))
    # Display estimate for UI only (actual billing uses real job duration).
    effective_rate = vm_rate
    cost_low = max(0.05, hours * effective_rate * 0.85)
    cost_high = max(cost_low + 0.05, hours * effective_rate * 1.2)

    if total_minutes < 90:
        duration = f"{total_minutes}–{total_minutes + 30} min"
    elif hours < 10:
        lo = max(1, int(hours * 0.85))
        hi = int(hours * 1.15) + 1
        duration = f"{lo}–{hi} hours"
    else:
        duration = f"{int(hours)}–{int(hours * 1.2)} hours"

    return {
        "estimated_duration": duration,
        "estimated_cost": f"${cost_low:.2f}–${cost_high:.2f}",
        "minutes_per_epoch": minutes_per_epoch,
    }


def _maybe_settle_training_credits(
    *,
    project_id: str,
    job_id: str,
    job_status: str,
    duration_seconds: Any,
    compute: Any,
    prev_training: dict[str, Any],
) -> None:
    """Debit Azure VM cost once when a job reaches a terminal state."""
    if job_status not in ("Completed", "Failed", "Cancelled"):
        return
    if prev_training.get("credits_settled"):
        return
    user_id = prev_training.get("billed_user_id")
    if user_id is None:
        logger.warning(
            "Training %s finished with no billed_user_id on project %s — compute not charged",
            job_id,
            project_id,
        )
        return
    vm_size = prev_training.get("vm_size") or configured_vm_size()
    session_id = prev_training.get("billed_session_id")
    try:
        result = settle_training_compute(
            user_id=int(user_id),
            job_id=str(job_id),
            project_id=project_id,
            duration_seconds=float(duration_seconds) if duration_seconds is not None else None,
            vm_size=str(vm_size) if vm_size else None,
            job_status=job_status,
            session_id=int(session_id) if session_id is not None else None,
        )
        patch: dict[str, Any] = {
            "training": {
                **prev_training,
                "job_id": job_id,
                "status": job_status,
                "credits_settled": True,
                "credits_settlement": result,
                "compute": compute or prev_training.get("compute"),
                "vm_size": vm_size,
            }
        }
        _project_store.update_meta(project_id, patch)
    except Exception as exc:
        logger.warning("Training credit settle failed for %s: %s", job_id, exc)


class SubmitTrainingRequest(BaseModel):
    project_id: str
    dataset_url: str = ""
    dataset_blob_key: str = ""
    task_type: str  # object_detection, classification, segmentation
    config: Dict[str, Any]


class TrainingStatusResponse(BaseModel):
    job_id: str
    status: str
    metrics: Optional[Dict[str, Any]]
    logs_url: str
    start_time: Optional[str]
    end_time: Optional[str]


class ModelInfo(BaseModel):
    name: str
    version: str
    description: Optional[str]
    tags: Dict[str, str]
    created_at: str


class MockMLService:
    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._job_counter = 0

    def submit_training_job(
        self,
        dataset_url: str,
        task_type: str,
        config: Dict[str, Any],
        project_id: str,
        dataset_blob_key: str | None = None,
    ):
        self._job_counter += 1
        job_id = f"mock-job-{self._job_counter}"
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": "Running",
            "display_name": f"Mock Training - {project_id}",
            "experiment": f"visiondock-{project_id}",
            "metrics": {
                "epoch": 50,
                "loss": 0.42,
                "mAP50": 0.68,
                "mAP50_95": 0.51,
                "precision": 0.72,
                "recall": 0.65,
            },
            "logs_url": "https://ml.azure.com",
            "start_time": "2024-01-01T00:00:00",
            "end_time": None,
            "compute": "mock",
        }
        return self._jobs[job_id]

    def get_job_status(self, job_id: str):
        return self._jobs.get(job_id, {"error": "Job not found"})

    def cancel_job(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "Cancelled"
            return True
        return False

    def list_models(self, project_id: Optional[str] = None):
        return []

    def deploy_model_endpoint(
        self,
        model_name: str,
        model_version: str,
        endpoint_name: str,
        config: Optional[Dict] = None,
    ):
        return {"endpoint_name": endpoint_name, "scoring_uri": "https://example.com/score"}


def _use_mock() -> bool:
    if os.getenv("TRAINING_MOCK", "").lower() in ("1", "true", "yes"):
        return True
    if not AZURE_ML_AVAILABLE:
        return True
    return False


def get_ml():
    """Get ML service (Azure or mock)."""
    if _use_mock():
        return MockMLService()
    try:
        return get_ml_service()
    except Exception as e:
        logger.warning(f"Azure ML init failed, using mock: {e}")
        return MockMLService()


def _resolve_dataset(project_id: str, dataset_url: str, dataset_blob_key: str) -> tuple[str, str]:
    """Load dataset blob key / URL from project meta when omitted."""
    meta = _project_store.get_meta(project_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Project not found")
    ds = meta.get("dataset") or {}
    if not ds.get("uploaded"):
        raise HTTPException(status_code=400, detail="Upload training images before starting training")
    if not ds.get("validated"):
        raise HTTPException(status_code=400, detail="Dataset is not validated yet")

    blob_key = dataset_blob_key or ds.get("storage_key") or ""
    if not blob_key and ds.get("file_name"):
        blob_key = f"projects/{project_id}/datasets/raw/{ds['file_name']}"
    if ds.get("mode") == "classification" and not blob_key:
        blob_key = f"projects/{project_id}/datasets/classification/"
    if ds.get("mode") == "multi_label" and not blob_key:
        blob_key = f"projects/{project_id}/datasets/multi_label/"
    if ds.get("mode") == "regression" and not blob_key:
        blob_key = f"projects/{project_id}/datasets/regression/"
    if ds.get("mode") in ("object_detection", "object_localization") and not blob_key:
        blob_key = ds.get("storage_key") or f"projects/{project_id}/datasets/annotated/raw/{ds.get('file_name', '')}"
    url = dataset_url or ds.get("blob_url") or ds.get("url") or ""
    return url, blob_key


@router.get("/info")
def training_info(epochs: int = 100):
    """Report whether Azure ML is wired and resolved GPU/compute details."""
    mode = "mock"
    workspace = os.getenv("AZURE_ML_WORKSPACE", "visiondock-ml")
    init_error: str | None = None
    compute_name = os.getenv("AZURE_ML_COMPUTE", "gpu-cluster")
    vm_size = os.getenv("AZURE_ML_VM_SIZE", "Standard_NC4as_T4_v3")
    epochs = max(1, min(epochs, 500))

    if not _use_mock():
        try:
            svc = get_ml_service()
            mode = "azure"
            try:
                cluster = svc.ml_client.compute.get(compute_name)
                vm_size = getattr(cluster, "size", None) or vm_size
            except Exception as e:
                logger.debug("Compute lookup: %s", e)
        except Exception as e:
            init_error = str(e)
            mode = "mock"

    profile = _VM_GPU_PROFILES.get(vm_size, {"gpu": vm_size, "vram_gb": None})
    estimates = _estimate_training(epochs, vm_size)
    env_id = os.getenv(
        "AZURE_ML_ENVIRONMENT",
        "azureml:AzureML-ACPT-pytorch-1.13-py38-cuda11.7-gpu:1",
    )

    return {
        "mode": mode,
        "sdk_installed": AZURE_ML_AVAILABLE,
        "sdk_import_error": AZURE_ML_IMPORT_ERROR,
        "init_error": init_error,
        "workspace": workspace,
        "resource_group": os.getenv("AZURE_RESOURCE_GROUP", "vision-doc"),
        "subscription_id_set": bool(os.getenv("AZURE_SUBSCRIPTION_ID")),
        "storage_configured": bool(
            os.getenv("AZURE_STORAGE_CONNECTION_STRING") or os.getenv("AZURE_STORAGE_CONNECTION")
        ),
        "compute": compute_name,
        "vm_size": vm_size,
        "gpu": profile.get("gpu"),
        "vram_gb": profile.get("vram_gb"),
        "environment": (
            env_id.replace("azureml:", "").split("@")[0] if env_id else None
        ),
        "location": os.getenv("AZURE_ML_LOCATION", "westeurope"),
        **estimates,
    }


def _planned_job_id(project_id: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"visiondock-train-{project_id}-{ts}"


def _project_id_from_job(job_id: str) -> str | None:
    match = re.match(r"visiondock-train-(prj-[a-f0-9]+)-", job_id)
    return match.group(1) if match else None


def _persist_training_status(status: dict[str, Any]) -> None:
    """Save job status + metrics on project meta when training finishes."""
    job_id = status.get("job_id")
    if not job_id:
        return
    project_id = _project_id_from_job(str(job_id))
    if not project_id:
        return

    job_status = str(status.get("status", ""))
    metrics = status.get("metrics") or {}
    if metrics:
        metrics = normalize_training_metrics(metrics)

    stored = _project_store.get_meta(project_id)
    stored_training = (stored or {}).get("training") or {}
    # Keep everything already on the record (billed_user_id, vm_size, credits_settled…);
    # a status poll must never drop the billing fields written at submit.
    carry_over = stored_training if stored_training.get("job_id") in (None, job_id) else {}

    def _keep(key: str) -> Any:
        return status.get(key) if status.get(key) is not None else carry_over.get(key)

    training_record: dict[str, Any] = {
        **carry_over,
        "job_id": job_id,
        "status": job_status,
        "status_message": status.get("status_message"),
        "display_name": _keep("display_name"),
        "experiment": _keep("experiment"),
        "compute": _keep("compute"),
        "start_time": _keep("start_time"),
        "end_time": _keep("end_time"),
        "duration_seconds": _keep("duration_seconds"),
        "metrics": metrics or carry_over.get("metrics") or {},
        "logs_url": status.get("logs_url") or status.get("job_url") or carry_over.get("logs_url"),
        "job_url": status.get("job_url") or status.get("logs_url") or carry_over.get("job_url"),
        "updated_at": datetime.utcnow().isoformat(),
    }

    meta_patch: dict[str, Any] = {"training": training_record}
    if job_status == "Completed":
        meta_patch["status"] = "training_complete"
        try:
            from services.inference_service import get_inference_service

            manifest = get_inference_service().model_artifacts_in_blob(project_id, str(job_id))
            if manifest:
                meta_patch["model"] = manifest
                tuned = manifest.get("tuned_thresholds")
                if isinstance(tuned, dict) and tuned:
                    try:
                        spec = _project_store.load_spec(project_id) or {}
                        post = dict(spec.get("postprocessing") or {})
                        if "confidence_threshold" in tuned:
                            post["confidence_threshold"] = float(tuned["confidence_threshold"])
                        if "nms_iou_threshold" in tuned:
                            post["nms_iou_threshold"] = float(tuned["nms_iou_threshold"])
                        spec["postprocessing"] = post
                        _project_store.save_spec(project_id, spec)
                    except Exception as exc:
                        logger.debug("Apply tuned thresholds to spec: %s", exc)
        except Exception as exc:
            logger.debug("Model manifest lookup: %s", exc)
    elif job_status in ("Failed", "Cancelled"):
        meta_patch["status"] = "training_failed"

    try:
        existing = _project_store.get_meta(project_id)
        if existing is None:
            return
        prev = existing.get("training") or {}
        if prev.get("job_id") == job_id and prev.get("status") == job_status and not metrics:
            if job_status not in ("Completed", "Failed", "Cancelled"):
                return
        if (
            job_status in ("Completed", "Failed", "Cancelled")
            or not prev.get("job_id")
            or prev.get("job_id") == job_id
        ):
            _project_store.update_meta(project_id, meta_patch)
            if job_status in ("Completed", "Failed", "Cancelled"):
                _maybe_settle_training_credits(
                    project_id=project_id,
                    job_id=str(job_id),
                    job_status=job_status,
                    duration_seconds=status.get("duration_seconds")
                    or prev.get("duration_seconds"),
                    compute=status.get("compute") or prev.get("compute"),
                    prev_training={**prev, **training_record},
                )
            # Deploy stays user-triggered: an endpoint bills Azure by the hour, so the
            # user must start it from the Inference page where the credits are debited.
    except Exception as exc:
        logger.warning("Failed to persist training status for %s: %s", project_id, exc)


@router.post("/submit")
async def submit_training(
    payload: SubmitTrainingRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Submit a new training job to Azure ML (returns immediately for Azure mode)."""
    require_project_access(
        _project_store.get_meta(payload.project_id),
        payload.project_id,
        session_user(request),
    )
    # Pre-check live DB balance for Azure VM reserve; actual debit on job end.
    balance_check = check_from_request(request, db, "training_submit")
    session = session_user(request)
    credit_user = ensure_user_row(db, session)
    credit_user_id = int(credit_user.id)
    credit_session_id = session.get("session_id")
    vm_size = configured_vm_size()
    try:
        spec = _project_store.load_spec(payload.project_id)
        resolved_task = (spec or {}).get("task_type") or payload.task_type or "classification"
        payload.task_type = resolved_task
        payload.config = merge_spec_pipeline_into_config(spec, payload.config)

        if resolved_task == "regression" and spec:
            payload.config["target_name"] = spec.get("target_name") or "target"
            payload.config["target_unit"] = spec.get("target_unit") or ""

        dataset_url, dataset_blob_key = _resolve_dataset(
            payload.project_id,
            payload.dataset_url,
            payload.dataset_blob_key,
        )

        if resolved_task in ("object_detection", "object_localization"):
            if not dataset_blob_key.endswith(".zip") and "/annotated/" not in dataset_blob_key:
                meta = _project_store.get_meta(payload.project_id) or {}
                ds = meta.get("dataset") or {}
                if ds.get("file_name"):
                    dataset_blob_key = ds.get("storage_key") or dataset_blob_key

        if _use_mock():
            logger.warning(
                "Training running in MOCK mode — install/configure Azure ML for real jobs"
            )
        elif not dataset_blob_key and os.getenv("STORAGE_BACKEND", "local") == "local":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Dataset is on local disk only. Set STORAGE_BACKEND=azure and "
                    "AZURE_STORAGE_CONNECTION_STRING on the App Service, then re-upload the ZIP."
                ),
            )

        mode = "mock" if _use_mock() else "azure"
        billing_fields = {
            "billed_user_id": credit_user_id,
            "billed_session_id": credit_session_id,
            "vm_size": vm_size,
            "credits_settled": False,
            "credits_reserved": balance_check["required"],
        }

        if mode == "mock":
            result = get_ml().submit_training_job(
                dataset_url=dataset_url,
                task_type=payload.task_type,
                config=payload.config,
                project_id=payload.project_id,
                dataset_blob_key=dataset_blob_key or None,
            )
            mock_job_id = str((result or {}).get("job_id") or f"mock-{payload.project_id}")
            try:
                _project_store.update_meta(
                    payload.project_id,
                    {
                        "training": {
                            "job_id": mock_job_id,
                            "status": "Completed",
                            "duration_seconds": 15 * 60,
                            **billing_fields,
                        }
                    },
                )
            except KeyError:
                pass
            credits = settle_training_compute(
                user_id=credit_user_id,
                job_id=mock_job_id,
                project_id=payload.project_id,
                duration_seconds=15 * 60,
                vm_size=vm_size,
                job_status="Completed",
                session_id=int(credit_session_id) if credit_session_id is not None else None,
            ) or {
                "balance": balance_check["balance"],
                "debited": 0,
                "reason": "training_compute",
            }
            return {
                "success": True,
                "data": jsonable_encoder(result),
                "mode": mode,
                "credits": credits,
            }

        job_id = _planned_job_id(payload.project_id)

        def _do_submit() -> dict[str, Any]:
            try:
                _project_store.update_meta(
                    payload.project_id,
                    {
                        "training": {
                            "job_id": job_id,
                            "status": "Submitting",
                            "display_name": f"VisionDock Training - {payload.project_id}",
                            "experiment": f"visiondock-{payload.project_id}",
                            "submitted_at": datetime.utcnow().isoformat(),
                            "compute": os.getenv("AZURE_ML_COMPUTE", "cpu-cluster"),
                            **billing_fields,
                        }
                    },
                )
            except KeyError:
                pass
            try:
                svc = get_ml_service()
                result = svc.submit_training_job(
                    dataset_url=dataset_url,
                    task_type=payload.task_type,
                    config=payload.config,
                    project_id=payload.project_id,
                    dataset_blob_key=dataset_blob_key or None,
                    planned_job_name=job_id,
                )
                # Record accept without debit — Azure compute billed when job ends.
                try:
                    SessionLocal = get_session_factory()
                    sdb = SessionLocal()
                    try:
                        record_usage_event(
                            sdb,
                            user_id=credit_user_id,
                            action="training_submit",
                            status="accepted",
                            credits_delta=0,
                            project_id=payload.project_id,
                            ref=job_id,
                            note=f"Azure ML accepted training job ({payload.task_type})",
                            session_id=int(credit_session_id)
                            if credit_session_id is not None
                            else None,
                            meta={"vm_size": vm_size, "task_type": payload.task_type},
                        )
                        sdb.commit()
                    finally:
                        sdb.close()
                except Exception as usage_exc:
                    logger.debug("training_submit usage event: %s", usage_exc)
                if isinstance(result, dict):
                    result = {
                        **result,
                        "credits": {
                            "balance": balance_check["balance"],
                            "debited": 0,
                            "pending": True,
                            "reason": "training_compute",
                            "note": "Credits charged from Azure VM duration when the job ends",
                        },
                    }
                return result
            except Exception as submit_exc:
                err_msg = str(submit_exc).strip() or "Training submission failed"
                try:
                    _project_store.update_meta(
                        payload.project_id,
                        {
                            "training": {
                                "job_id": job_id,
                                "status": "Failed",
                                "display_name": f"VisionDock Training - {payload.project_id}",
                                "experiment": f"visiondock-{payload.project_id}",
                                "error": err_msg,
                                "failed_at": datetime.utcnow().isoformat(),
                                "credits_settled": True,
                                **billing_fields,
                            }
                        },
                    )
                except KeyError:
                    pass
                raise

        start_submission(job_id, _do_submit)

        return {
            "success": True,
            "data": {
                "job_id": job_id,
                "status": "Submitting",
                "display_name": f"VisionDock Training - {payload.project_id}",
                "experiment": f"visiondock-{payload.project_id}",
                "compute": os.getenv("AZURE_ML_COMPUTE", "cpu-cluster"),
                "vm_size": vm_size,
                "start_time": datetime.utcnow().isoformat(),
            },
            "mode": mode,
            "credits": {
                "balance": balance_check["balance"],
                "debited": 0,
                "pending_debit_estimate": cost_for("training_submit"),
                "reason": "training_compute",
                "note": (
                    "Balance reserved for ~Azure VM time; "
                    "actual debit = job duration × VM $/hr when the job ends"
                ),
                "pricing": {
                    "vm_size": vm_size,
                    "vm_hourly_usd": vm_hourly_usd(vm_size),
                },
            },
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to submit training job: {e}")
        msg = str(e).strip() or "Training submission failed"
        raise HTTPException(status_code=500, detail=msg) from e


def _status_response(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("metrics"):
        status["metrics"] = normalize_training_metrics(status["metrics"])
    _persist_training_status(status)
    return {"success": True, "data": jsonable_encoder(status)}


@router.get("/status/{job_id}")
async def get_training_status(job_id: str):
    """Get the current status of a training job."""
    try:
        err = peek_error(job_id) or get_submission_error(job_id)
        if err:
            failed = {
                "job_id": job_id,
                "status": "Failed",
                "display_name": job_id,
                "experiment": "",
                "metrics": {},
                "error": err,
                "phase": "submit_failed",
            }
            _persist_training_status(failed)
            return _status_response(failed)

        queued = peek_submission_result(job_id)
        project_id = _project_id_from_job(job_id)

        def _mark_stale_submit_failed(reason: str) -> dict[str, Any] | None:
            if not project_id:
                return None
            meta = _project_store.get_meta(project_id) or {}
            training = meta.get("training") or {}
            if (
                training.get("job_id") == job_id
                and str(training.get("status", "")).lower() == "submitting"
            ):
                stale = {
                    "job_id": job_id,
                    "status": "Failed",
                    "display_name": training.get("display_name") or job_id,
                    "experiment": training.get("experiment") or "",
                    "metrics": {},
                    "error": reason,
                    "phase": "submit_stale",
                }
                _persist_training_status(stale)
                return stale
            return None

        if not _use_mock():
            try:
                status = get_ml_service().get_job_status(job_id)
                if "error" not in status:
                    clear_submission_result(job_id)
                    return _status_response(status)
            except Exception as exc:
                logger.debug("AML live status for %s: %s", job_id, exc)

        if is_inflight(job_id):
            return {
                "success": True,
                "data": {
                    "job_id": job_id,
                    "status": "Submitting",
                    "display_name": job_id,
                    "experiment": "",
                    "metrics": {},
                    "phase": "registering",
                    "compute": os.getenv("AZURE_ML_COMPUTE", "cpu-cluster"),
                },
            }

        if _use_mock():
            ml = get_ml()
        else:
            ml = get_ml_service()
        try:
            status = ml.get_job_status(job_id)
        except Exception as exc:
            stale = _mark_stale_submit_failed(
                "Training submission did not complete (job was never registered in Azure ML). "
                "Start training again."
            )
            if stale:
                return _status_response(stale)
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if "error" in status:
            if queued:
                return {"success": True, "data": jsonable_encoder(queued)}
            stale = _mark_stale_submit_failed(
                "Training submission did not complete (server restarted or "
                "submit failed). Start training again."
            )
            if stale:
                return _status_response(stale)
            raise HTTPException(status_code=404, detail=status["error"])

        clear_submission_result(job_id)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/cancel/{job_id}")
async def cancel_training(job_id: str):
    """Cancel a running training job."""
    try:
        ml = get_ml()
        success = ml.cancel_job(job_id)

        return {
            "success": success,
            "message": "Job cancelled" if success else "Failed to cancel job",
        }
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/models")
async def list_models(project_id: Optional[str] = None):
    """List trained models in the registry."""
    try:
        ml = get_ml()
        models = ml.list_models(project_id=project_id)

        return {"success": True, "data": models}
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/deploy")
async def deploy_model(
    model_name: str,
    model_version: str,
    endpoint_name: Optional[str] = None,
):
    """Deploy a trained model as a managed endpoint."""
    try:
        ml = get_ml()

        if not endpoint_name:
            endpoint_name = f"{model_name}-endpoint"

        result = ml.deploy_model_endpoint(
            model_name=model_name,
            model_version=model_version,
            endpoint_name=endpoint_name,
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deploy model: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
