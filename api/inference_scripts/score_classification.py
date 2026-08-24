"""Azure ML managed endpoint scoring for EfficientNet vision tasks."""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms

model = None
class_names: list[str] = []
task_type = "classification"
imgsz = 224
device = torch.device("cpu")
target_name = "target"
target_unit = ""
target_mean = 0.0
target_std = 1.0
_pipeline: dict | None = None
_default_confidence = 0.5


def _find_weights() -> str:
    model_dir = os.getenv("AZUREML_MODEL_DIR", ".")
    candidates = list(Path(model_dir).rglob("*.pt"))
    if not candidates:
        raise FileNotFoundError(f"No .pt weights under {model_dir}")
    return str(candidates[0])


def _load_sidecar(model_dir: Path) -> dict:
    for name in ("labels.json", "model.json"):
        path = model_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def _build_model(model_name: str, num_outputs: int) -> nn.Module:
    if model_name == "efficientnet_b2":
        backbone = models.efficientnet_b2(weights=None)
        in_features = backbone.classifier[1].in_features
        backbone.classifier[1] = nn.Linear(in_features, num_outputs)
        return backbone
    backbone = models.efficientnet_b0(weights=None)
    in_features = backbone.classifier[1].in_features
    backbone.classifier[1] = nn.Linear(in_features, num_outputs)
    return backbone


def init() -> None:
    global model, class_names, task_type, imgsz, device
    global target_name, target_unit, target_mean, target_std
    global _pipeline, _default_confidence

    model_dir = Path(os.getenv("AZUREML_MODEL_DIR", "."))
    weights_path = _find_weights()
    checkpoint = torch.load(weights_path, map_location="cpu")
    sidecar = _load_sidecar(model_dir)

    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        state = checkpoint["model_state_dict"]
        class_names = list(checkpoint.get("classes") or sidecar.get("classes") or [])
        model_name = str(checkpoint.get("model_name") or "efficientnet_b0")
        imgsz = int(checkpoint.get("imgsz") or 224)
        task_type = str(
            checkpoint.get("task_type") or sidecar.get("task_type") or "classification"
        )
        target_name = str(
            checkpoint.get("target_name") or sidecar.get("target_name") or "target"
        )
        target_unit = str(
            checkpoint.get("target_unit") or sidecar.get("target_unit") or ""
        )
        target_mean = float(
            checkpoint.get("target_mean") if checkpoint.get("target_mean") is not None
            else sidecar.get("target_mean", 0.0)
        )
        target_std = float(
            checkpoint.get("target_std") if checkpoint.get("target_std") is not None
            else sidecar.get("target_std", 1.0)
        )
        if isinstance(checkpoint.get("preprocessing"), dict):
            _pipeline = {"preprocessing": checkpoint["preprocessing"]}
    else:
        raise ValueError("Expected checkpoint with model_state_dict")

    sidecar_pipeline = sidecar.get("pipeline") if isinstance(sidecar.get("pipeline"), dict) else None
    if sidecar_pipeline:
        _pipeline = sidecar_pipeline
    model_json = model_dir / "model.json"
    if model_json.exists():
        try:
            manifest = json.loads(model_json.read_text(encoding="utf-8"))
            if isinstance(manifest.get("pipeline"), dict):
                _pipeline = manifest["pipeline"]
        except (json.JSONDecodeError, OSError):
            pass

    from visiondock_postprocess import load_postprocess_config

    post = load_postprocess_config(_pipeline)
    _default_confidence = post.confidence_threshold

    if not class_names and task_type != "regression":
        raise ValueError("No class labels found in checkpoint or labels.json")
    if task_type == "regression":
        num_outputs = 1
    else:
        num_outputs = len(class_names)

    model = _build_model(model_name, num_outputs)
    model.load_state_dict(state)
    model.eval()

    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        model = model.to(device)


def _decode_image(payload: dict) -> Image.Image:
    if "image_base64" in payload:
        raw = base64.b64decode(payload["image_base64"])
        return Image.open(io.BytesIO(raw)).convert("RGB")
    if "image_url" in payload:
        import urllib.request

        with urllib.request.urlopen(payload["image_url"], timeout=30) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    raise ValueError("Provide image_base64 or image_url")


def _preprocess(image: Image.Image) -> torch.Tensor:
    from visiondock_preprocess import apply_pil_preprocess, load_preprocess_config

    cfg = load_preprocess_config(_pipeline)
    if cfg.imgsz != imgsz:
        cfg.imgsz = imgsz
    image = apply_pil_preprocess(image, cfg)
    normalize = transforms.Normalize(mean=list(cfg.normalize_mean), std=list(cfg.normalize_std))
    tf = transforms.Compose(
        [
            transforms.Resize((imgsz, imgsz)),
            transforms.ToTensor(),
            normalize,
        ]
    )
    return tf(image).unsqueeze(0)


def _run_classification(payload: dict, tensor: torch.Tensor) -> dict:
    top_k = int(payload.get("top_k", min(5, len(class_names))))
    top_k = max(1, min(top_k, len(class_names)))
    min_conf = float(
        payload.get("confidence", payload.get("confidence_threshold", _default_confidence))
    )

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.softmax(logits, dim=1)[0]

    values, indices = torch.topk(probs, k=top_k)
    predictions = []
    for conf, idx in zip(values.tolist(), indices.tolist()):
        if conf < min_conf:
            continue
        predictions.append(
            {
                "class_id": int(idx),
                "class_name": class_names[idx] if idx < len(class_names) else str(idx),
                "confidence": float(conf),
            }
        )
    top_class = predictions[0] if predictions else None
    return {
        "task_type": "classification",
        "predictions": predictions,
        "top_class": top_class,
        "count": len(predictions),
        "confidence_threshold": min_conf,
    }


def _run_multi_label(payload: dict, tensor: torch.Tensor) -> dict:
    threshold = float(payload.get("confidence", payload.get("threshold", 0.5)))

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.sigmoid(logits)[0]

    active = []
    for idx, score in enumerate(probs.tolist()):
        if score >= threshold:
            active.append(
                {
                    "label": class_names[idx] if idx < len(class_names) else str(idx),
                    "confidence": float(score),
                }
            )
    active.sort(key=lambda x: -x["confidence"])
    return {
        "task_type": "multi_label",
        "labels": active,
        "count": len(active),
        "threshold": threshold,
    }


def _run_regression(_payload: dict, tensor: torch.Tensor) -> dict:
    with torch.no_grad():
        output = model(tensor)[0, 0].item()
    value = output * target_std + target_mean
    return {
        "task_type": "regression",
        "target_name": target_name,
        "target_unit": target_unit,
        "value": float(value),
        "prediction": float(value),
    }


def run(raw_data: str) -> str:
    if model is None:
        raise RuntimeError("Model not initialized")

    payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    if isinstance(payload, list):
        payload = payload[0]

    image = _decode_image(payload)
    tensor = _preprocess(image).to(device)

    if task_type == "multi_label":
        result = _run_multi_label(payload, tensor)
    elif task_type == "regression":
        result = _run_regression(payload, tensor)
    else:
        result = _run_classification(payload, tensor)

    return json.dumps(result)
