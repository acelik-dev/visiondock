"""Register trained models and deploy Azure ML managed online endpoints."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from services.project_store import ProjectStore

logger = logging.getLogger(__name__)

_deploy_lock = threading.Lock()
_deploy_inflight: set[str] = set()
_deploy_errors: dict[str, str] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_endpoint_name(project_id: str) -> str:
    base = re.sub(r"[^a-z0-9-]", "", project_id.lower().replace("_", "-"))
    name = f"vd-{base}"[:32].rstrip("-")
    return name or "vd-project"


def generate_visiondock_api_key() -> str:
    return f"vd_{secrets.token_urlsafe(24)}"


def _friendly_deploy_error(exc: BaseException | str) -> str:
    msg = str(exc).strip()
    if "OutOfQuota" in msg:
        return (
            "Azure CPU quota is insufficient for the inference VM size. "
            "Request a quota increase for West Europe Standard FS/DS series, or set "
            "AZURE_ML_INFERENCE_VM=Standard_F2s_v2 on the App Service and retry."
        )
    if "SubscriptionNotRegistered" in msg or "isn't registered with Subscription" in msg:
        return (
            "Azure subscription is missing resource providers for managed endpoints "
            "(often Microsoft.Cdn, Microsoft.PolicyInsights, Microsoft.Network, Microsoft.Compute). "
            "Run ./scripts/register-azure-inference-providers.sh on the subscription, then retry deploy."
        )
    return msg or "Inference deploy failed"


class InferenceService:
    def __init__(self, store: ProjectStore | None = None) -> None:
        self.store = store or ProjectStore()

    def get_inference_meta(self, project_id: str) -> dict[str, Any]:
        meta = self.store.get_meta(project_id)
        if not meta:
            raise KeyError(project_id)
        return meta.get("inference") or {}

    def ensure_api_key(self, project_id: str, rotate: bool = False) -> str:
        meta = self.store.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        inference = dict(meta.get("inference") or {})
        if inference.get("api_key") and not rotate:
            return str(inference["api_key"])
        api_key = generate_visiondock_api_key()
        inference["api_key"] = api_key
        inference["api_key_created_at"] = _now()
        self.store.update_meta(project_id, {"inference": inference})
        return api_key

    def _model_prefix(self, project_id: str, job_id: str) -> str:
        return f"projects/{project_id}/models/{job_id}"

    def model_artifacts_in_blob(self, project_id: str, job_id: str) -> dict[str, Any]:
        prefix = self._model_prefix(project_id, job_id)
        manifest_key = f"{prefix}/model.json"
        manifest = self.store.store.read_json(manifest_key)
        if not isinstance(manifest, dict):
            return {}
        return manifest

    def model_size_bytes(self, project_id: str, job_id: str) -> int | None:
        """Registered artifact size — drives the deploy credit cost."""
        manifest = self.model_artifacts_in_blob(project_id, job_id)
        total = 0
        for key in ("weights_blob", "onnx_blob"):
            blob_key = manifest.get(key)
            if not blob_key:
                continue
            size = self.store.store.size_bytes(str(blob_key))
            if size:
                total += int(size)
        return total or None

    def register_and_deploy(
        self,
        project_id: str,
        job_id: str,
        *,
        billing_factory: Callable[[], dict[str, Any]] | None = None,
    ) -> bool:
        """Start a deploy in the background. Returns False if one is already running."""
        with _deploy_lock:
            if project_id in _deploy_inflight:
                return False
            _deploy_inflight.add(project_id)
            _deploy_errors.pop(project_id, None)

            try:
                billing = billing_factory() if billing_factory is not None else None
            except Exception:
                _deploy_inflight.discard(project_id)
                raise

            def _refund_billing(note: str) -> None:
                if billing is None:
                    return
                try:
                    from services.credits import refund_debit_for_user_id

                    refund_debit_for_user_id(
                        user_id=int(billing["user_id"]),
                        debit_usage_event_id=int(billing["debit_usage_event_id"]),
                        session_id=(
                            int(billing["session_id"])
                            if billing.get("session_id") is not None
                            else None
                        ),
                        note=note,
                    )
                except Exception:
                    logger.exception("Inference deploy refund failed for %s", project_id)

            def _run() -> None:
                try:
                    self._register_and_deploy_sync(project_id, job_id)
                except Exception as exc:
                    logger.exception("Inference deploy failed for %s", project_id)
                    _deploy_errors[project_id] = _friendly_deploy_error(exc)
                    try:
                        self.store.update_meta(
                            project_id,
                            {
                                "inference": {
                                    **self.get_inference_meta(project_id),
                                    "status": "failed",
                                    "error": _deploy_errors[project_id],
                                    "updated_at": _now(),
                                }
                            },
                        )
                    finally:
                        _refund_billing(
                            f"Refund for failed inference deployment: {_deploy_errors[project_id]}"
                        )
                finally:
                    with _deploy_lock:
                        _deploy_inflight.discard(project_id)

            try:
                thread = threading.Thread(
                    target=_run,
                    name=f"inference-deploy-{project_id}",
                    daemon=True,
                )
                thread.start()
            except Exception:
                _deploy_inflight.discard(project_id)
                _refund_billing("Refund because inference deployment thread failed to start")
                raise
        return True

    def deploy_status(self, project_id: str) -> dict[str, Any]:
        if project_id in _deploy_inflight:
            return {"status": "deploying"}
        if project_id in _deploy_errors:
            return {"status": "failed", "error": _deploy_errors[project_id]}
        return self.get_inference_meta(project_id)

    def _register_and_deploy_sync(self, project_id: str, job_id: str) -> dict[str, Any]:
        from services.azure_ml_service import get_ml_service

        api_key = self.ensure_api_key(project_id)
        manifest = self.model_artifacts_in_blob(project_id, job_id)
        weights_bytes: bytes | None = None
        onnx_bytes: bytes | None = None

        if manifest.get("weights_blob"):
            weights_bytes = self.store.store.read_bytes(manifest["weights_blob"])
            if manifest.get("onnx_blob"):
                onnx_bytes = self.store.store.read_bytes(manifest["onnx_blob"])

        if not weights_bytes:
            weights_bytes, manifest = self._download_weights_from_aml_job(project_id, job_id)

        if not weights_bytes:
            raise ValueError(
                "Model weights not found. Re-run training with the latest script, or wait for artifact upload."
            )

        inference_patch: dict[str, Any] = {
            "status": "deploying",
            "job_id": job_id,
            "api_key": api_key,
            "updated_at": _now(),
        }
        self.store.update_meta(project_id, {"inference": inference_patch, "status": "inference_deploying"})

        weights_key = manifest.get("weights_blob") or f"projects/{project_id}/models/{job_id}/best.pt"
        if not manifest.get("weights_blob"):
            self.store.store.write_bytes(weights_key, weights_bytes)
            manifest = {
                **manifest,
                "project_id": project_id,
                "job_id": job_id,
                "weights_blob": weights_key,
            }
            self.store.store.write_json(
                f"projects/{project_id}/models/{job_id}/model.json",
                manifest,
            )

        spec = self.store.load_spec(project_id) or {}
        task_type = str(
            manifest.get("task_type") or spec.get("task_type") or "classification"
        )
        if task_type in ("object_detection", "object_localization"):
            task_type = "object_detection"

        ml = get_ml_service()
        model_name = f"vd-{project_id.replace('_', '-')}"[:255]
        endpoint_name = _sanitize_endpoint_name(project_id)

        labels_key = manifest.get("labels_blob") or f"projects/{project_id}/models/{job_id}/labels.json"
        labels_bytes: bytes | None = None
        try:
            labels_bytes = self.store.store.read_bytes(labels_key)
        except Exception:
            labels_bytes = None

        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp) / "model"
            model_dir.mkdir()
            (model_dir / "best.pt").write_bytes(weights_bytes)
            if onnx_bytes:
                (model_dir / "best.onnx").write_bytes(onnx_bytes)
            if labels_bytes:
                (model_dir / "labels.json").write_bytes(labels_bytes)
            post_merged = {
                **(spec.get("postprocessing") or {}),
                **(manifest.get("tuned_thresholds") or {}),
            }
            pipeline: dict[str, Any] = {
                "preprocessing": spec.get("preprocessing") or {},
                "postprocessing": post_merged,
            }
            if isinstance(manifest.get("pipeline"), dict):
                saved = manifest["pipeline"]
                pipeline = {
                    "preprocessing": {
                        **pipeline["preprocessing"],
                        **(saved.get("preprocessing") or {}),
                    },
                    "postprocessing": {
                        **pipeline["postprocessing"],
                        **(saved.get("postprocessing") or {}),
                    },
                }
            manifest = {**manifest, "pipeline": pipeline}
            (model_dir / "model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            (model_dir / "pipeline.json").write_text(json.dumps(pipeline, indent=2), encoding="utf-8")

            registered = ml.register_model_folder(
                model_name=model_name,
                model_path=str(model_dir),
                project_id=project_id,
                job_id=job_id,
            )

            deploy_result = ml.deploy_managed_endpoint(
                endpoint_name=endpoint_name,
                model_name=registered["name"],
                model_version=str(registered["version"]),
                project_id=project_id,
                task_type=task_type,
            )
            if "error" in deploy_result:
                raise RuntimeError(deploy_result["error"])

        post = spec.get("postprocessing") or {}
        tuned = manifest.get("tuned_thresholds") or {}
        if isinstance(tuned, dict):
            if tuned.get("confidence_threshold") is not None:
                post = {**post, "confidence_threshold": float(tuned["confidence_threshold"])}
            if tuned.get("nms_iou_threshold") is not None:
                post = {**post, "nms_iou_threshold": float(tuned["nms_iou_threshold"])}

        final: dict[str, Any] = {
            "status": "deployed",
            "job_id": job_id,
            "task_type": task_type,
            "model_name": registered["name"],
            "model_version": registered["version"],
            "endpoint_name": deploy_result["endpoint_name"],
            "scoring_uri": deploy_result["scoring_uri"],
            "swagger_uri": deploy_result.get("swagger_uri"),
            "aml_primary_key": deploy_result.get("primary_key"),
            "api_key": api_key,
            "confidence_threshold": post.get("confidence_threshold", 0.5),
            "nms_iou_threshold": post.get("nms_iou_threshold", 0.5),
            "tta": bool(post.get("tta", False)),
            "ensemble": bool(post.get("ensemble", False)),
            "sahi": bool(post.get("sahi", False)),
            "sahi_slice_size": int(post.get("sahi_slice_size", 640)),
            "sahi_overlap_ratio": float(post.get("sahi_overlap_ratio", 0.2)),
            "weights_blob": weights_key,
            "onnx_blob": manifest.get("onnx_blob"),
            "metrics": manifest.get("metrics"),
            "deployed_at": _now(),
            "updated_at": _now(),
        }
        self.store.update_meta(
            project_id,
            {"inference": final, "status": "inference_ready", "model": manifest},
        )
        return final

    def _download_weights_from_aml_job(
        self, project_id: str, job_id: str
    ) -> tuple[bytes | None, dict[str, Any]]:
        """Fallback: extract best.pt from completed AML job logs/artifacts."""
        from services.azure_ml_service import get_ml_service

        manifest: dict[str, Any] = {"project_id": project_id, "job_id": job_id}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ml = get_ml_service()
                ml.ml_client.jobs.download(name=job_id, download_path=tmp)
                tmp_path = Path(tmp)
                for log_file in tmp_path.rglob("std_log.txt"):
                    text = log_file.read_text(errors="ignore")
                    model_match = re.search(r"VISIONDOCK_MODEL:\s*(\{[^\n]+\})", text)
                    if model_match:
                        try:
                            manifest = json.loads(model_match.group(1))
                        except json.JSONDecodeError:
                            pass
                for pt in tmp_path.rglob("best.pt"):
                    return pt.read_bytes(), manifest
        except Exception as exc:
            logger.debug("AML job artifact download for %s: %s", job_id, exc)
        return None, manifest

    def build_edge_bundle(self, project_id: str) -> bytes:
        meta = self.store.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        inference = meta.get("inference") or {}
        if inference.get("status") != "deployed" and not meta.get("model"):
            raise ValueError("No trained model available for edge export")

        model_meta = meta.get("model") or {}
        job_id = inference.get("job_id") or model_meta.get("job_id")
        if not job_id:
            raise ValueError("Missing job_id for model artifacts")

        manifest = model_meta or self.model_artifacts_in_blob(project_id, job_id)
        weights_key = manifest.get("weights_blob") or manifest.get("onnx_blob")
        if not weights_key:
            raise ValueError("Model files missing in storage")

        weights = self.store.store.read_bytes(weights_key)
        if not weights:
            raise ValueError("Could not read model weights")

        onnx_key = manifest.get("onnx_blob")
        onnx = self.store.store.read_bytes(onnx_key) if onnx_key else None

        api_key = inference.get("api_key") or self.ensure_api_key(project_id)
        spec = self.store.load_spec(project_id) or {}
        task_type = str(
            inference.get("task_type") or manifest.get("task_type") or spec.get("task_type") or "classification"
        )
        if task_type in ("object_detection", "object_localization"):
            task_type = "object_detection"

        scripts_dir = Path(__file__).resolve().parent.parent / "inference_scripts"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if onnx:
                zf.writestr("model/best.onnx", onnx)
            else:
                zf.writestr("model/best.pt", weights)
            zf.writestr("model/model.json", json.dumps(manifest, indent=2))
            zf.writestr("model/project-spec.json", json.dumps(spec, indent=2))
            labels_blob = manifest.get("labels_blob") or f"projects/{project_id}/models/{job_id}/labels.json"
            try:
                labels_bytes = self.store.store.read_bytes(labels_blob)
            except Exception:
                labels_bytes = None
            if labels_bytes:
                zf.writestr("model/labels.json", labels_bytes)
            zf.write(scripts_dir / "Dockerfile.edge", "Dockerfile")
            zf.write(scripts_dir / "score_server.py", "score_server.py")
            zf.write(scripts_dir / "visiondock_preprocess.py", "visiondock_preprocess.py")
            zf.write(scripts_dir / "visiondock_postprocess.py", "visiondock_postprocess.py")
            if task_type == "object_detection":
                zf.write(scripts_dir / "tiled_detection.py", "tiled_detection.py")
                zf.write(scripts_dir / "ensemble_detection.py", "ensemble_detection.py")
            pipeline = manifest.get("pipeline") or {
                "preprocessing": spec.get("preprocessing") or {},
                "postprocessing": spec.get("postprocessing") or {},
            }
            zf.writestr("model/pipeline.json", json.dumps(pipeline, indent=2))
            edge_readme = (
                "VisionDock Edge Inference (x86 Docker)\n\n"
                "Note: The bundled FastAPI server uses the legacy YOLO path. "
                "For classification models, use the Cloud API (Azure ML) endpoint instead.\n\n"
                "1. unzip visiondock-edge.zip\n"
                "2. cp .env.example .env and set VISIONDOCK_API_KEY\n"
                f"3. docker build -t visiondock-edge:{project_id} .\n"
                f"4. docker run -p 8080:8080 --env-file .env visiondock-edge:{project_id}\n"
                "5. POST image to http://localhost:8080/predict with header X-API-Key\n"
            )
            if task_type in ("classification", "multi_label", "regression"):
                zf.write(scripts_dir / "score_classification.py", "score_classification.py")
                edge_readme += (
                    f"\n{task_type.replace('_', ' ').title()} model included — "
                    "score_classification.py is bundled for reference; "
                    "integrate it into a custom edge server or use the managed cloud endpoint.\n"
                )
            post = (pipeline.get("postprocessing") if isinstance(pipeline, dict) else None) or spec.get("postprocessing") or {}
            pre = (pipeline.get("preprocessing") if isinstance(pipeline, dict) else None) or spec.get("preprocessing") or {}
            conf_thr = post.get("confidence_threshold", inference.get("confidence_threshold", 0.5))
            iou_thr = post.get("nms_iou_threshold", inference.get("nms_iou_threshold", 0.5))
            tta = bool(post.get("tta", inference.get("tta", False)))
            ensemble = bool(post.get("ensemble", inference.get("ensemble", False)))
            sahi = bool(post.get("sahi", inference.get("sahi", False)))
            zf.writestr(
                ".env.example",
                (
                    "VISIONDOCK_API_KEY=your-key-here\n"
                    f"CONFIDENCE_THRESHOLD={conf_thr}\n"
                    f"NMS_IOU_THRESHOLD={iou_thr}\n"
                    f"TTA={'true' if tta else 'false'}\n"
                    f"ENSEMBLE={'true' if ensemble else 'false'}\n"
                    f"SAHI={'true' if sahi else 'false'}\n"
                    f"SAHI_SLICE_SIZE={post.get('sahi_slice_size', 640)}\n"
                    f"SAHI_OVERLAP_RATIO={post.get('sahi_overlap_ratio', 0.2)}\n"
                    f"PREPROCESS_GRAYSCALE={'true' if pre.get('grayscale') else 'false'}\n"
                    f"PREPROCESS_DENOISE={'true' if pre.get('denoise') else 'false'}\n"
                    f"PREPROCESS_CONTRAST={'true' if pre.get('contrast_enhancement') else 'false'}\n"
                    f"PREPROCESS_AUTO_ORIENT={'true' if pre.get('auto_orientation', True) else 'false'}\n"
                    "MODEL_PATH=/app/model/best.onnx\n"
                ),
            )
            zf.writestr("README.txt", edge_readme)
            zf.writestr("api_key.txt", api_key)
        buf.seek(0)
        return buf.read()


_inference_service: InferenceService | None = None


def get_inference_service() -> InferenceService:
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service
