"""Azure ML Service for VisionDock AI model training."""
import json
import os
import logging
import re
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from azure.ai.ml import MLClient, command
from azure.ai.ml.entities import JobResourceConfiguration
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ResourceNotFoundError

from services.pipeline_env import pipeline_env_from_spec

logger = logging.getLogger(__name__)


def _metrics_to_dict(raw: Any) -> dict[str, Any]:
    """Azure ML metrics objects are not JSON-serializable by default."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        flat: dict[str, Any] = {}
        for key, value in raw.items():
            if isinstance(value, list) and value:
                try:
                    flat[str(key)] = max(
                        value,
                        key=lambda item: getattr(item, "step", 0) if not isinstance(item, dict) else item.get("step", 0),
                    )
                    if hasattr(flat[str(key)], "value"):
                        flat[str(key)] = flat[str(key)].value
                    elif isinstance(flat[str(key)], dict):
                        flat[str(key)] = flat[str(key)].get("value")
                except (TypeError, ValueError):
                    flat[str(key)] = value[-1]
            else:
                flat[str(key)] = value
        return flat

    series: dict[str, list[tuple[int, Any]]] = {}
    try:
        for item in raw:
            name = getattr(item, "name", None) or getattr(item, "metric_name", None)
            value = getattr(item, "value", None)
            if name is None:
                continue
            step = getattr(item, "step", None)
            if step is None:
                step = 0
            series.setdefault(str(name), []).append((int(step), value))
    except TypeError:
        return {}

    return {name: pairs[-1][1] for name, pairs in series.items()}


def normalize_training_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    """Map AML / Ultralytics metric names to stable VisionDock keys."""
    if not raw:
        return {}

    def _pick(*keys: str) -> float | None:
        for key in keys:
            if key in raw and raw[key] is not None:
                try:
                    return float(raw[key])
                except (TypeError, ValueError):
                    continue
        return None

    out: dict[str, Any] = {}
    mAP50 = _pick("mAP50", "metrics/mAP50(B)", "map50", "mAP", "map_50")
    mAP50_95 = _pick("mAP50_95", "mAP50-95", "metrics/mAP50-95(B)", "map", "map_50_95")
    precision = _pick("precision", "metrics/precision(B)")
    recall = _pick("recall", "metrics/recall(B)")
    loss = _pick("loss", "train/box_loss", "val/box_loss")
    epoch = _pick("epoch", "epochs")

    if mAP50 is not None:
        out["mAP50"] = mAP50
        out["mAP"] = mAP50
    if mAP50_95 is not None:
        out["mAP50_95"] = mAP50_95
    if precision is not None:
        out["precision"] = precision
    if recall is not None:
        out["recall"] = recall
    if loss is not None:
        out["loss"] = loss
    if epoch is not None:
        out["epoch"] = int(epoch)

    accuracy = _pick("accuracy", "val_accuracy", "top1_accuracy", "metrics/accuracy")
    val_accuracy = _pick("val_accuracy", "metrics/val_accuracy")
    if accuracy is not None:
        out["accuracy"] = accuracy
    if val_accuracy is not None:
        out["val_accuracy"] = val_accuracy
    if accuracy is None and val_accuracy is not None:
        out["accuracy"] = val_accuracy

    f1 = _pick("f1", "micro_f1", "metrics/f1", "metrics/micro_f1")
    macro_f1 = _pick("macro_f1", "metrics/macro_f1")
    if f1 is not None:
        out["f1"] = f1
        out["micro_f1"] = f1
    if macro_f1 is not None:
        out["macro_f1"] = macro_f1

    mae = _pick("mae", "metrics/mae", "val_mae")
    rmse = _pick("rmse", "metrics/rmse", "val_rmse")
    mse = _pick("mse", "metrics/mse")
    r2 = _pick("r2", "metrics/r2", "val_r2")
    if mae is not None:
        out["mae"] = mae
    if rmse is not None:
        out["rmse"] = rmse
    if mse is not None:
        out["mse"] = mse
    if r2 is not None:
        out["r2"] = r2

    return out


def _iso_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _iso_duration_seconds(value: str | None) -> float | None:
    """Parse AML ISO-8601 durations like PT16M59.42S into seconds."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().upper()
    if not text.startswith("P"):
        return None
    hours = minutes = seconds = 0.0
    m = re.match(
        r"^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$",
        text,
    )
    if not m:
        return None
    if m.group(1):
        hours += float(m.group(1)) * 24
    if m.group(2):
        hours += float(m.group(2))
    if m.group(3):
        minutes += float(m.group(3))
    if m.group(4):
        seconds += float(m.group(4))
    total = hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def _as_utc(value: str) -> datetime | None:
    """AML mixes tz-aware ISO strings with naive UTC ones ("2026-08-13 09:09:30")."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _prop(props: Any, *names: str) -> Any:
    """AML returns job.properties as a dict on real jobs and as an object in some SDK paths."""
    for name in names:
        value = props.get(name) if isinstance(props, dict) else getattr(props, name, None)
        if value is not None:
            return value
    return None


def _extract_job_times(job: Any) -> dict[str, Any]:
    """Best-effort start/end/duration from AML job (Studio uses properties, not created_at)."""
    start: str | None = None
    end: str | None = None
    duration_seconds: float | None = None

    props = getattr(job, "properties", None)
    if props is not None:
        start = _iso_dt(_prop(props, "start_time", "started_on", "startTime", "StartTimeUtc"))
        end = _iso_dt(_prop(props, "end_time", "completed_on", "endTime", "EndTimeUtc"))
        duration_seconds = _iso_duration_seconds(_prop(props, "duration", "Duration"))

    ctx = getattr(job, "creation_context", None)
    if ctx is not None:
        if not start:
            start = _iso_dt(getattr(ctx, "created_at", None))
        if not end:
            end = _iso_dt(getattr(ctx, "end_time", None))

    if duration_seconds is None and start and end:
        try:
            started = _as_utc(start)
            ended = _as_utc(end)
            if started and ended:
                duration_seconds = (ended - started).total_seconds()
        except (TypeError, ValueError):
            pass
    if duration_seconds is not None and duration_seconds <= 0:
        duration_seconds = None

    return {
        "start_time": start,
        "end_time": end,
        "duration_seconds": duration_seconds,
    }


_metrics_cache: dict[str, dict[str, Any]] = {}


def _parse_visiondock_metrics_blob(text: str) -> dict[str, Any]:
    match = re.search(r"VISIONDOCK_METRICS:\s*(\{[^\n]+\})", text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


class AzureMLService:
    """Handles Azure ML operations for model training and deployment."""
    
    def __init__(self):
        self.subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        self.resource_group = os.getenv("AZURE_RESOURCE_GROUP", "vision-doc")
        self.workspace_name = os.getenv("AZURE_ML_WORKSPACE", "visiondock-ml")
        self.compute_name = os.getenv("AZURE_ML_COMPUTE", "gpu-cluster")
        self.vm_size = os.getenv("AZURE_ML_VM_SIZE", "Standard_NC4as_T4_v3")

        if not self.subscription_id:
            raise ValueError("AZURE_SUBSCRIPTION_ID is required for Azure ML")

        # Try DefaultAzureCredential first, fallback to env vars
        try:
            credential = DefaultAzureCredential()
            self.ml_client = MLClient(
                credential=credential,
                subscription_id=self.subscription_id,
                resource_group_name=self.resource_group,
                workspace_name=self.workspace_name
            )
            logger.info(f"Azure ML client initialized for workspace: {self.workspace_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Azure ML client: {e}")
            raise

    def _workspace_studio_id(self) -> str:
        """Workspace path for ml.azure.com ?wsid= (resourcegroups is lowercase in Studio URLs)."""
        return (
            f"/subscriptions/{self.subscription_id}"
            f"/resourcegroups/{self.resource_group.lower()}"
            f"/providers/Microsoft.MachineLearningServices"
            f"/workspaces/{self.workspace_name}"
        )

    def _mlflow_tracking_uri(self) -> str:
        return (
            f"azureml://subscriptions/{self.subscription_id}"
            f"/resourcegroups/{self.resource_group.lower()}"
            f"/providers/Microsoft.MachineLearningServices/workspaces/{self.workspace_name}"
        )

    def _metrics_from_mlflow(self, job_id: str, experiment: str) -> dict[str, Any]:
        """AML v2 command jobs expose metrics via MLflow, not jobs.get_metrics."""
        try:
            import mlflow

            mlflow.set_tracking_uri(self._mlflow_tracking_uri())
            client = mlflow.tracking.MlflowClient()
            filters = (
                f"attributes.run_id = '{job_id}'",
                f"tags.mlflow.runName = '{job_id}'",
            )
            for filt in filters:
                runs = client.search_runs(
                    experiment_names=[experiment] if experiment else None,
                    filter_string=filt,
                    max_results=1,
                )
                if runs:
                    return dict(runs[0].data.metrics)

            if experiment:
                for run in client.search_runs(experiment_names=[experiment], max_results=50):
                    if run.info.run_name == job_id or run.info.run_id == job_id:
                        return dict(run.data.metrics)
        except Exception as exc:
            logger.debug("MLflow metrics for %s: %s", job_id, exc)
        return {}

    def _metrics_from_job_logs(self, job_id: str) -> dict[str, Any]:
        """Parse VISIONDOCK_METRICS line from downloaded stdout log."""
        if job_id in _metrics_cache:
            return _metrics_cache[job_id]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                self.ml_client.jobs.download(name=job_id, download_path=tmp)
                for path in Path(tmp).rglob("std_log.txt"):
                    raw = _parse_visiondock_metrics_blob(path.read_text(errors="ignore"))
                    if raw:
                        _metrics_cache[job_id] = raw
                        return raw
        except Exception as exc:
            logger.debug("Log metrics for %s: %s", job_id, exc)
        return {}

    def _resolve_job_metrics(self, job_id: str, experiment: str, status: str) -> dict[str, Any]:
        if job_id in _metrics_cache:
            return normalize_training_metrics(_metrics_cache[job_id])

        raw: dict[str, Any] = {}
        try:
            raw = _metrics_to_dict(self.ml_client.jobs.get_metrics(job_id))
        except Exception as exc:
            logger.debug("jobs.get_metrics for %s: %s", job_id, exc)

        normalized = normalize_training_metrics(raw)
        if normalized:
            _metrics_cache[job_id] = normalized
            return normalized

        if status not in ("Running", "Finalizing", "Completed"):
            return {}

        mlflow_raw = self._metrics_from_mlflow(job_id, experiment)
        if mlflow_raw:
            normalized = normalize_training_metrics(mlflow_raw)
            if normalized:
                _metrics_cache[job_id] = normalized
                return normalized

        if status == "Completed":
            log_raw = self._metrics_from_job_logs(job_id)
            normalized = normalize_training_metrics(log_raw)
            if normalized:
                _metrics_cache[job_id] = normalized
                return normalized

        return {}

    def studio_run_url(self, job_name: str) -> str:
        """Deep link to job run in Azure ML Studio; without wsid Studio redirects to home."""
        params = f"wsid={self._workspace_studio_id()}"
        tid = os.getenv("AZURE_ML_STUDIO_TENANT_ID", "").strip()
        if tid:
            params += f"&tid={tid}"
        return f"https://ml.azure.com/runs/{job_name}?{params}"

    @staticmethod
    def _normalize_job_status(raw: Any) -> str:
        """Map AML enums like Status.QUEUED → Queued for the UI."""
        text = str(raw or "Unknown")
        token = text.split(".")[-1] if "." in text else text
        mapping = {
            "QUEUED": "Queued",
            "NOTSTARTED": "Queued",
            "STARTING": "Starting",
            "PREPARING": "Starting",
            "RUNNING": "Running",
            "FINALIZING": "Finalizing",
            "COMPLETED": "Completed",
            "FAILED": "Failed",
            "CANCELED": "Cancelled",
            "CANCELLED": "Cancelled",
        }
        return mapping.get(token.upper(), token)

    @staticmethod
    def _job_status_message(job: Any, status: str) -> str | None:
        """Human-readable queue / resize hint from AML job properties."""
        props = getattr(job, "properties", None)
        if isinstance(props, dict):
            for key in ("statusMessage", "status_message", "StatusMessage"):
                msg = props.get(key)
                if msg:
                    return str(msg)

        for attr in ("status_message", "status_details"):
            val = getattr(job, attr, None)
            if val:
                return str(val)

        if status in ("Queued", "Starting"):
            compute = getattr(job, "compute", None) or os.getenv("AZURE_ML_COMPUTE", "gpu-cluster")
            return (
                f"Waiting for GPU node on '{compute}'. "
                "The cluster scales up from zero after idle — this usually takes 3–8 minutes."
            )
        return None

    @staticmethod
    def _studio_url_from_job(job: Any) -> str | None:
        services = getattr(job, "services", None)
        if not services:
            return None
        studio = (
            services.get("Studio")
            if isinstance(services, dict)
            else getattr(services, "Studio", None)
        )
        if isinstance(studio, dict):
            return studio.get("endpoint")
        return getattr(studio, "endpoint", None)
    
    def ensure_compute(
        self,
        compute_name: str | None = None,
        vm_size: str | None = None,
    ) -> Any:
        """Return existing compute cluster (must be created in Studio/CLI)."""
        compute_name = compute_name or self.compute_name
        vm_size = vm_size or self.vm_size
        try:
            compute = self.ml_client.compute.get(compute_name)
            logger.info(f"Using existing compute: {compute_name}")
            return compute
        except ResourceNotFoundError as exc:
            raise ValueError(
                f"Compute cluster '{compute_name}' was not found in workspace "
                f"'{self.workspace_name}'. Create it once in Azure ML Studio "
                f"(Compute → Create → AML compute → name: {compute_name}, "
                f"VM size: {vm_size or self.vm_size}), then retry training."
            ) from exc
    
    def get_or_create_environment(self, task_type: str = "yolov8") -> str:
        """Return environment id for training (curated GPU base + pip deps in job command)."""
        env_name = f"visiondock-{task_type}-env"
        try:
            env = self.ml_client.environments.get(env_name, label="latest")
            logger.info(f"Using existing environment: {env_name}")
            return f"azureml:{env_name}:latest"
        except ResourceNotFoundError:
            logger.info(f"Using workspace PyTorch GPU environment for {task_type}")
            # Must exist in workspace — @latest curated names often are not registered
            return os.getenv(
                "AZURE_ML_ENVIRONMENT",
                "azureml:AzureML-ACPT-pytorch-1.13-py38-cuda11.7-gpu:1",
            )
    
    def submit_training_job(
        self,
        dataset_url: str,
        task_type: str,
        config: Dict[str, Any],
        project_id: str,
        dataset_blob_key: str | None = None,
        planned_job_name: str | None = None,
    ) -> Dict[str, Any]:
        """Submit a model training job to Azure ML."""
        if not dataset_blob_key:
            raise ValueError(
                "dataset_blob_key is required — upload a dataset to the project first"
            )

        storage_conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING") or os.getenv(
            "AZURE_STORAGE_CONNECTION", ""
        )
        if not storage_conn:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING is required so the training job can read the dataset"
            )

        is_efficientnet_task = task_type in (
            "classification",
            "multi_label",
            "regression",
        )
        # Use configured compute name directly — avoid a slow ARM lookup on every submit.
        compute_name = self.compute_name
        env_id = os.getenv(
            "AZURE_ML_ENVIRONMENT",
            "azureml:AzureML-ACPT-pytorch-1.13-py38-cuda11.7-gpu:1",
        )

        job_name = planned_job_name or (
            f"visiondock-train-{project_id}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        api_root = Path(__file__).resolve().parent.parent
        code_dir = api_root / "training_scripts"

        epochs = config.get("epochs", 50)
        imgsz = config.get("imgsz", 224 if is_efficientnet_task else 640)
        batch = config.get("batch", 16)
        lr = config.get("learning_rate", 0.001)
        val_split = config.get("validation_split", 0.2)
        model_name = config.get("model_name", "efficientnet_b0")

        pipeline_env = pipeline_env_from_spec(
            {
                "preprocessing": config.get("preprocessing"),
                "postprocessing": config.get("postprocessing"),
            },
            config,
            int(imgsz),
        )

        common_env = {
            "AZURE_STORAGE_CONNECTION_STRING": storage_conn,
            "AZURE_STORAGE_CONTAINER": os.getenv("AZURE_STORAGE_CONTAINER", "visiondock"),
            "TASK_TYPE": task_type,
            "PROJECT_ID": project_id,
            "JOB_NAME": job_name,
            "EPOCHS": str(epochs),
            "IMGSZ": str(imgsz),
            "BATCH": str(batch),
            "LEARNING_RATE": str(lr),
            "VAL_SPLIT": str(val_split),
            "MODEL_NAME": model_name,
            "DEVICE": os.getenv("AZURE_ML_DEVICE", "0"),
            "MLFLOW_TRACKING_URI": os.getenv("MLFLOW_TRACKING_URI", ""),
            "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION": "python",
            "AUGMENTATION": "1" if config.get("augmentation", True) else "0",
            "MIXUP_ENABLED": "1" if config.get("mixup") else "0",
            "CUTMIX_ENABLED": "1" if config.get("cutmix") else "0",
            "LABEL_SMOOTHING": str(config.get("label_smoothing", 0.0)),
            "AUTO_TUNE_THRESHOLDS": "1"
            if config.get("auto_tune_thresholds", True)
            else "0",
            **pipeline_env,
        }
        pip_deps = (
            "pip install -q 'protobuf==3.20.3' torchvision azure-storage-blob pillow mlflow && "
        )

        if task_type == "classification":
            train_cmd = pip_deps + "python aml_train_classification.py"
            if dataset_blob_key.lower().endswith(".zip"):
                env_vars = {
                    **common_env,
                    "DATASET_BLOB_KEY": dataset_blob_key,
                }
            else:
                classification_prefix = dataset_blob_key
                if not classification_prefix.endswith("/"):
                    classification_prefix += "/"
                env_vars = {
                    **common_env,
                    "CLASSIFICATION_PREFIX": classification_prefix,
                    "DATASET_BLOB_KEY": classification_prefix,
                }
        elif task_type == "multi_label":
            multi_label_prefix = dataset_blob_key
            if not multi_label_prefix.endswith("/"):
                multi_label_prefix += "/"
            train_cmd = pip_deps + "python aml_train_multi_label.py"
            env_vars = {
                **common_env,
                "MULTI_LABEL_PREFIX": multi_label_prefix,
                "DATASET_BLOB_KEY": multi_label_prefix,
            }
        elif task_type == "regression":
            regression_prefix = dataset_blob_key
            if not regression_prefix.endswith("/"):
                regression_prefix += "/"
            train_cmd = pip_deps + "python aml_train_regression.py"
            env_vars = {
                **common_env,
                "REGRESSION_PREFIX": regression_prefix,
                "DATASET_BLOB_KEY": regression_prefix,
                "TARGET_NAME": str(config.get("target_name") or "target"),
                "TARGET_UNIT": str(config.get("target_unit") or ""),
                "LOSS_TYPE": str(config.get("loss_type") or "mse"),
            }
        else:
            train_cmd = (
                "pip install -q 'protobuf==3.20.3' ultralytics azure-storage-blob pyyaml mlflow onnx onnxruntime && "
                "python aml_train_yolo.py"
            )
            yolo_weights = (
                config.get("yolo_weights")
                or config.get("model_name")
                or config.get("recommended_model")
                or "yolov8m.pt"
            )
            patience = config.get("patience", config.get("early_stopping_patience", 20))
            env_vars = {
                **common_env,
                "DATASET_BLOB_KEY": dataset_blob_key,
                "DATASET_URL": dataset_url or "",
                "YOLO_WEIGHTS": str(yolo_weights),
                "PATIENCE": str(patience),
                "OPTIMIZER": str(config.get("optimizer", "AdamW")),
                "COS_LR": "1" if str(config.get("scheduler", "cosine")).lower() == "cosine" else "0",
            }

        job = command(
            name=job_name,
            display_name=f"VisionDock Training - {project_id}",
            description=f"Training {task_type} model for project {project_id}",
            code=str(code_dir),
            command=train_cmd,
            environment=env_id,
            compute=compute_name,
            experiment_name=f"visiondock-{project_id}",
            resources=JobResourceConfiguration(
                instance_count=config.get("nodes", 1),
                shm_size="32g",
            ),
            environment_variables=env_vars,
            tags={
                "project_id": project_id,
                "task_type": task_type,
            },
        )

        submitted_job = self.ml_client.jobs.create_or_update(job)

        logger.info(f"Training job submitted: {submitted_job.name}")

        return {
            "job_id": submitted_job.name,
            "display_name": submitted_job.display_name,
            "job_url": self.studio_run_url(submitted_job.name),
            "logs_url": self.studio_run_url(submitted_job.name),
            "status": self._normalize_job_status(submitted_job.status),
            "compute": compute_name,
            "environment": env_id,
            "experiment": submitted_job.experiment_name,
            "start_time": datetime.utcnow().isoformat(),
            "submitted_at": datetime.utcnow().isoformat(),
        }
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get current status of a training job."""
        try:
            job = self.ml_client.jobs.get(job_id)
            
            status = self._normalize_job_status(job.status)
            experiment = job.experiment_name or ""
            metrics = self._resolve_job_metrics(job_id, experiment, status)
            times = _extract_job_times(job)
            return {
                "job_id": job.name,
                "status": status,
                "status_message": self._job_status_message(job, status),
                "display_name": job.display_name,
                "experiment": job.experiment_name,
                "start_time": times["start_time"],
                "end_time": times["end_time"],
                "duration_seconds": times["duration_seconds"],
                "compute": str(job.compute) if hasattr(job, 'compute') and job.compute else None,
                "metrics": metrics,
                "logs_url": self._studio_url_from_job(job) or self.studio_run_url(job.name),
                "job_url": self._studio_url_from_job(job) or self.studio_run_url(job.name),
            }
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            return {"error": str(e)}
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running training job."""
        try:
            self.ml_client.jobs.begin_cancel(job_id).wait()
            logger.info(f"Job cancelled: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job: {e}")
            return False
    
    def list_models(self, project_id: Optional[str] = None) -> list:
        """List trained models in the registry."""
        try:
            models = self.ml_client.models.list()
            result = []
            for model in models:
                if project_id is None or project_id in (model.tags.get("project_id", "")):
                    result.append({
                        "name": model.name,
                        "version": model.version,
                        "description": model.description,
                        "tags": model.tags,
                        "created_at": model.creation_context.created_at.isoformat() if model.creation_context.created_at else None
                    })
            return result
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    def register_model_folder(
        self,
        model_name: str,
        model_path: str,
        project_id: str,
        job_id: str,
    ) -> Dict[str, Any]:
        """Register a local model folder (best.pt) in the AML model registry."""
        from azure.ai.ml.entities import Model

        try:
            model = Model(
                name=model_name,
                path=model_path,
                description=f"VisionDock YOLO model for {project_id}",
                tags={"project_id": project_id, "job_id": job_id},
            )
            registered = self.ml_client.models.create_or_update(model)
            logger.info("Registered model %s v%s", registered.name, registered.version)
            return {
                "name": registered.name,
                "version": str(registered.version),
            }
        except Exception as exc:
            logger.error("Model registration failed: %s", exc)
            raise

    def deploy_managed_endpoint(
        self,
        endpoint_name: str,
        model_name: str,
        model_version: str,
        project_id: str,
        task_type: str = "classification",
    ) -> Dict[str, Any]:
        """Deploy scoring to an Azure ML managed online endpoint."""
        from azure.ai.ml.entities import (
            CodeConfiguration,
            Environment,
            ManagedOnlineDeployment,
            ManagedOnlineEndpoint,
            OnlineRequestSettings,
        )

        try:
            api_root = Path(__file__).resolve().parent.parent
            code_dir = api_root / "inference_scripts"
            is_yolo = task_type in ("object_detection", "object_localization")

            if not is_yolo:
                conda = code_dir / "conda-classification.yaml"
                env_name = "visiondock-classification-inference-v1"
                scoring_script = "score_classification.py"
                env_description = "EfficientNet image classification inference (torchvision)"
            else:
                conda = code_dir / "conda.yaml"
                env_name = "visiondock-yolo-inference-v5"
                scoring_script = "score_yolo.py"
                env_description = "Ultralytics YOLO inference (headless OpenCV, conda)"

            try:
                env_obj = self.ml_client.environments.get(env_name, label="latest")
            except ResourceNotFoundError:
                env_obj = self.ml_client.environments.create_or_update(
                    Environment(
                        name=env_name,
                        description=env_description,
                        conda_file=str(conda),
                        image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04:latest",
                    )
                )
            env_id = f"azureml:{env_obj.name}:{env_obj.version}"

            try:
                existing = self.ml_client.online_endpoints.get(endpoint_name)
                if getattr(existing, "provisioning_state", None) == "Failed":
                    logger.warning("Deleting failed endpoint %s before redeploy", endpoint_name)
                    self.ml_client.online_endpoints.begin_delete(endpoint_name).result()
            except ResourceNotFoundError:
                pass

            endpoint = ManagedOnlineEndpoint(
                name=endpoint_name,
                description=f"VisionDock inference for {project_id}",
                auth_mode="key",
                tags={"project_id": project_id, "model": model_name},
            )
            self.ml_client.online_endpoints.begin_create_or_update(endpoint).result()

            try:
                bad = self.ml_client.online_deployments.get(
                    name="default", endpoint_name=endpoint_name
                )
                if getattr(bad, "provisioning_state", None) == "Failed":
                    logger.warning("Deleting failed deployment default on %s", endpoint_name)
                    self.ml_client.online_deployments.begin_delete(
                        name="default", endpoint_name=endpoint_name
                    ).result()
            except ResourceNotFoundError:
                pass

            deployment = ManagedOnlineDeployment(
                name="default",
                endpoint_name=endpoint_name,
                model=f"azureml:{model_name}:{model_version}",
                environment=env_id,
                code_configuration=CodeConfiguration(
                    code=str(code_dir),
                    scoring_script=scoring_script,
                ),
                instance_type=os.getenv("AZURE_ML_INFERENCE_VM", "Standard_F2s_v2"),
                instance_count=1,
                request_settings=OnlineRequestSettings(request_timeout_ms=90000),
            )
            self.ml_client.online_deployments.begin_create_or_update(
                deployment, skip_validation=True
            ).result()

            endpoint_obj = self.ml_client.online_endpoints.get(endpoint_name)
            endpoint_obj.traffic = {"default": 100}
            self.ml_client.online_endpoints.begin_create_or_update(endpoint_obj).result()
            endpoint_obj = self.ml_client.online_endpoints.get(endpoint_name)
            keys = self.ml_client.online_endpoints.get_keys(endpoint_name)

            return {
                "endpoint_name": endpoint_name,
                "scoring_uri": endpoint_obj.scoring_uri,
                "primary_key": keys.primary_key,
                "secondary_key": keys.secondary_key,
                "swagger_uri": getattr(endpoint_obj, "swagger_uri", None),
            }
        except Exception as e:
            logger.error(f"Failed to deploy endpoint: {e}")
            return {"error": str(e)}

    def deploy_model_endpoint(
        self,
        model_name: str,
        model_version: str,
        endpoint_name: str,
        deployment_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Legacy wrapper."""
        project_id = (deployment_config or {}).get("project_id", "unknown")
        task_type = (deployment_config or {}).get("task_type", "classification")
        return self.deploy_managed_endpoint(
            endpoint_name=endpoint_name,
            model_name=model_name,
            model_version=model_version,
            project_id=project_id,
            task_type=task_type,
        )
    
# Singleton instance
_ml_service: Optional[AzureMLService] = None


def get_ml_service() -> AzureMLService:
    """Get or create Azure ML service singleton."""
    global _ml_service
    if _ml_service is None:
        _ml_service = AzureMLService()
    return _ml_service
