"""Run on Azure ML compute: download dataset ZIP from blob, train YOLOv8."""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

# ONNX/protobuf on curated AML images often needs the pure-Python protobuf backend.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from azure.storage.blob import BlobServiceClient
from ultralytics import YOLO


def _download_dataset_zip() -> Path:
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or os.environ.get(
        "AZURE_STORAGE_CONNECTION", ""
    )
    key = os.environ.get("DATASET_BLOB_KEY", "")
    container = os.environ.get("AZURE_STORAGE_CONTAINER", "visiondock")
    if not conn or not key:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING and DATASET_BLOB_KEY are required")

    client = BlobServiceClient.from_connection_string(conn)
    raw = client.get_container_client(container).download_blob(key).readall()

    root = Path("/tmp/visiondock_dataset")
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(root)
    return root


def _find_data_yaml(root: Path) -> Path:
    candidates = list(root.rglob("data.yaml"))
    if not candidates:
        raise FileNotFoundError(f"data.yaml not found under {root}")
    return candidates[0]


def _normalize_data_yaml(data_yaml: Path, root: Path) -> Path:
    """Rewrite relative train/val paths so YOLO finds images after ZIP extract."""
    import yaml

    with data_yaml.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return data_yaml

    for key in ("train", "val", "valid", "test"):
        rel = data.get(key)
        if not rel or not isinstance(rel, str):
            continue
        p = Path(rel)
        if p.is_absolute() and p.exists():
            continue
        for base in (data_yaml.parent, root, data_yaml.parent.parent):
            candidate = (base / rel).resolve()
            if candidate.exists():
                data[key] = str(candidate)
                break

    if "valid" in data and "val" not in data:
        data["val"] = data["valid"]

    fixed = data_yaml.parent / "data.visiondock.yaml"
    with fixed.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return fixed


def _extract_metrics(results: object, epochs: int) -> dict[str, float]:
    """Pull final validation metrics from Ultralytics results."""
    rd: dict = getattr(results, "results_dict", None) or {}
    if not rd and hasattr(results, "metrics"):
        m = results.metrics
        if hasattr(m, "box"):
            box = m.box
            return {
                "mAP50": float(getattr(box, "map50", 0) or 0),
                "mAP50_95": float(getattr(box, "map", 0) or 0),
                "precision": float(getattr(box, "mp", 0) or 0),
                "recall": float(getattr(box, "mr", 0) or 0),
                "epoch": float(epochs),
            }

    return {
        "mAP50": float(rd.get("metrics/mAP50(B)", rd.get("metrics/mAP50", 0)) or 0),
        "mAP50_95": float(rd.get("metrics/mAP50-95(B)", rd.get("metrics/mAP50-95", 0)) or 0),
        "precision": float(rd.get("metrics/precision(B)", rd.get("metrics/precision", 0)) or 0),
        "recall": float(rd.get("metrics/recall(B)", rd.get("metrics/recall", 0)) or 0),
        "epoch": float(epochs),
    }


def _log_metrics(metrics: dict[str, float]) -> None:
    """Log to MLflow (Azure ML surfaces these via jobs.get_metrics) and stdout."""
    print(f"VISIONDOCK_METRICS: {json.dumps(metrics)}", flush=True)
    try:
        import mlflow

        for name, value in metrics.items():
            mlflow.log_metric(name, float(value))
    except Exception as exc:
        print(f"mlflow log skipped: {exc}", flush=True)


def _export_onnx(model: YOLO) -> str | None:
    """Best-effort ONNX export — training must succeed even if export fails."""
    try:
        path = model.export(format="onnx")
        print(f"ONNX export complete: {path}", flush=True)
        return str(path) if path else None
    except Exception as exc:
        print(f"ONNX export skipped (best.pt weights are still saved): {exc}", flush=True)
        return None


def _export_torchscript(model: YOLO) -> str | None:
    try:
        path = model.export(format="torchscript")
        print(f"TorchScript export complete: {path}", flush=True)
        return str(path) if path else None
    except Exception as exc:
        print(f"TorchScript export skipped: {exc}", flush=True)
        return None


def _export_artifacts(model: YOLO) -> dict[str, str | None]:
    from visiondock_preprocess import export_formats_from_env

    formats = {f.lower() for f in export_formats_from_env()}
    exports: dict[str, str | None] = {}
    if "onnx" in formats:
        exports["onnx"] = _export_onnx(model)
    if "torchscript" in formats:
        exports["torchscript"] = _export_torchscript(model)
    if not exports:
        exports["onnx"] = _export_onnx(model)
    return exports


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key) or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return default


def _env_float(key: str, default: float | None = None) -> float | None:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return float(raw)


def resolve_yolo_weights(task_type: str, model_name: str = "") -> str:
    """Map ProjectSpec recommended_model / yolo_weights to Ultralytics checkpoint."""
    task = task_type or "object_detection"
    suffix = {
        "classification": "-cls.pt",
        "segmentation": "-seg.pt",
    }.get(task, ".pt")

    m = (model_name or "").lower().strip()
    if m.endswith(".pt"):
        return m

    for family in ("yolo11", "yolov10", "yolov9", "yolov8"):
        for size in ("n", "s", "m", "l", "x"):
            token = f"{family}{size}"
            if token in m.replace("-", "").replace("_", ""):
                return f"{token}{suffix}"

    defaults = {
        "object_detection": "yolov8m.pt",
        "object_localization": "yolov8n.pt",
        "classification": "yolov8n-cls.pt",
        "segmentation": "yolov8n-seg.pt",
    }
    return defaults.get(task, "yolov8m.pt")


def _build_train_kwargs() -> dict:
    """Ultralytics hyperparameters from AML environment variables."""
    kwargs: dict = {"close_mosaic": int(os.environ.get("CLOSE_MOSAIC", "10"))}

    lr0 = _env_float("LEARNING_RATE") or _env_float("LR0")
    if lr0 is not None:
        kwargs["lr0"] = lr0

    patience = os.environ.get("PATIENCE")
    if patience:
        kwargs["patience"] = int(patience)

    optimizer = os.environ.get("OPTIMIZER")
    if optimizer:
        kwargs["optimizer"] = optimizer

    kwargs["cos_lr"] = _env_bool("COS_LR", True)

    if not _env_bool("AUGMENTATION", True):
        kwargs["mosaic"] = 0.0
        kwargs["mixup"] = 0.0
    elif _env_bool("MIXUP_ENABLED"):
        kwargs["mixup"] = _env_float("MIXUP", 0.1) or 0.1

    label_smoothing = _env_float("LABEL_SMOOTHING")
    if label_smoothing is not None and label_smoothing > 0:
        kwargs["label_smoothing"] = label_smoothing

    return kwargs


def tune_detection_thresholds(model, data_yaml: str, imgsz: int) -> dict[str, float]:
    """Grid-search conf/iou on the validation split (mAP50)."""
    if not _env_bool("AUTO_TUNE_THRESHOLDS", True):
        return {}

    best_score = -1.0
    best: dict[str, float] = {"confidence_threshold": 0.25, "nms_iou_threshold": 0.5}
    for conf in (0.15, 0.25, 0.35, 0.45, 0.55):
        for iou in (0.4, 0.5, 0.6, 0.7):
            try:
                metrics = model.val(data=data_yaml, imgsz=imgsz, conf=conf, iou=iou, verbose=False)
                box = getattr(metrics, "box", None)
                score = float(getattr(box, "map50", 0) or 0) if box is not None else 0.0
                if score > best_score:
                    best_score = score
                    best = {
                        "confidence_threshold": float(conf),
                        "nms_iou_threshold": float(iou),
                        "tune_map50": score,
                    }
            except Exception as exc:
                print(f"Threshold tune skipped conf={conf} iou={iou}: {exc}", flush=True)

    print(f"VISIONDOCK_THRESHOLDS: {json.dumps(best)}", flush=True)
    return best


def _find_best_weights() -> Path | None:
    for pattern in ("runs/detect/train/weights/best.pt", "runs/detect/train*/weights/best.pt"):
        matches = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]
    return None


def _upload_artifacts(
    project_id: str,
    job_name: str,
    weights_path: Path,
    export_paths: dict[str, str | None],
    metrics: dict[str, float],
    task_type: str,
    tuned_thresholds: dict[str, float] | None = None,
    pipeline: dict | None = None,
) -> None:
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or os.environ.get(
        "AZURE_STORAGE_CONNECTION", ""
    )
    container = os.environ.get("AZURE_STORAGE_CONTAINER", "visiondock")
    if not conn or not project_id or not job_name:
        print("Artifact upload skipped: missing storage or project/job id", flush=True)
        return

    prefix = f"projects/{project_id}/models/{job_name}"
    client = BlobServiceClient.from_connection_string(conn)
    blob = client.get_container_client(container).get_blob_client(f"{prefix}/best.pt")
    blob.upload_blob(weights_path.read_bytes(), overwrite=True)

    onnx_blob = None
    onnx_path = export_paths.get("onnx")
    if onnx_path and Path(onnx_path).exists():
        onnx_blob = f"{prefix}/best.onnx"
        client.get_container_client(container).get_blob_client(onnx_blob).upload_blob(
            Path(onnx_path).read_bytes(), overwrite=True
        )

    torchscript_blob = None
    ts_path = export_paths.get("torchscript")
    if ts_path and Path(ts_path).exists():
        torchscript_blob = f"{prefix}/best.torchscript.pt"
        client.get_container_client(container).get_blob_client(torchscript_blob).upload_blob(
            Path(ts_path).read_bytes(), overwrite=True
        )

    manifest = {
        "project_id": project_id,
        "job_id": job_name,
        "task_type": task_type,
        "weights_blob": f"{prefix}/best.pt",
        "onnx_blob": onnx_blob,
        "torchscript_blob": torchscript_blob,
        "metrics": metrics,
    }
    if tuned_thresholds:
        manifest["tuned_thresholds"] = tuned_thresholds
    if pipeline:
        manifest["pipeline"] = pipeline
    manifest_key = f"{prefix}/model.json"
    client.get_container_client(container).get_blob_client(manifest_key).upload_blob(
        json.dumps(manifest).encode("utf-8"), overwrite=True
    )
    print(f"VISIONDOCK_MODEL: {json.dumps(manifest)}", flush=True)


def main() -> None:
    from visiondock_preprocess import preprocess_config_from_env, preprocess_yolo_dataset
    from visiondock_postprocess import load_postprocess_config

    root = _download_dataset_zip()
    data_yaml = _normalize_data_yaml(_find_data_yaml(root), root)
    preprocess_cfg = preprocess_config_from_env()
    data_yaml = preprocess_yolo_dataset(data_yaml, preprocess_cfg)
    pipeline = {
        "preprocessing": preprocess_cfg.to_dict(),
        "postprocessing": load_postprocess_config().to_dict(),
    }
    task_type = os.environ.get("TASK_TYPE", "object_detection")
    epochs = int(os.environ.get("EPOCHS", "50"))
    imgsz = int(os.environ.get("IMGSZ", "640"))
    batch = int(os.environ.get("BATCH", "16"))
    weights = resolve_yolo_weights(
        task_type,
        os.environ.get("YOLO_WEIGHTS") or os.environ.get("MODEL_NAME", ""),
    )

    device = os.environ.get("DEVICE", "0")
    train_kwargs = _build_train_kwargs()
    print(f"Training {weights} epochs={epochs} imgsz={imgsz} batch={batch} kwargs={train_kwargs}", flush=True)
    model = YOLO(weights)
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        **train_kwargs,
    )
    metrics = _extract_metrics(results, epochs)
    _log_metrics(metrics)
    tuned = tune_detection_thresholds(model, str(data_yaml), imgsz)
    export_paths = _export_artifacts(model)
    project_id = os.environ.get("PROJECT_ID", "")
    job_name = os.environ.get("JOB_NAME", "")
    best = _find_best_weights()
    if best and project_id and job_name:
        if tuned:
            pipeline["postprocessing"] = {
                **pipeline["postprocessing"],
                **{k: v for k, v in tuned.items() if k in ("confidence_threshold", "nms_iou_threshold")},
            }
        _upload_artifacts(
            project_id,
            job_name,
            best,
            export_paths,
            metrics,
            task_type,
            tuned or None,
            pipeline,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Training failed: {exc}", flush=True)
        raise SystemExit(1) from exc
