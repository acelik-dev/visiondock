"""Azure ML managed endpoint scoring script for YOLOv8 object detection."""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from visiondock_postprocess import (
    load_postprocess_config,
    merge_payload_postprocess,
    run_yolo_detection,
)
from visiondock_preprocess import apply_pil_preprocess, load_preprocess_config

model = None
_pipeline: dict | None = None


def _find_weights() -> str:
    model_dir = os.getenv("AZUREML_MODEL_DIR", ".")
    candidates = list(Path(model_dir).rglob("*.pt"))
    if not candidates:
        raise FileNotFoundError(f"No .pt weights under {model_dir}")
    return str(candidates[0])


def _load_pipeline() -> dict | None:
    model_dir = Path(os.getenv("AZUREML_MODEL_DIR", "."))
    for name in ("model.json", "pipeline.json"):
        path = model_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("pipeline"), dict):
                return data["pipeline"]
        except (json.JSONDecodeError, OSError):
            continue
    return None


def init() -> None:
    global model, _pipeline
    os.environ.setdefault("YOLO_VERBOSE", "False")
    from ultralytics import YOLO

    model = YOLO(_find_weights())
    _pipeline = _load_pipeline()


def _decode_image(payload: dict) -> Image.Image:
    if "image_base64" in payload:
        raw = base64.b64decode(payload["image_base64"])
        return Image.open(io.BytesIO(raw)).convert("RGB")
    if "image_url" in payload:
        import urllib.request

        with urllib.request.urlopen(payload["image_url"], timeout=30) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    raise ValueError("Provide image_base64 or image_url")


def run(raw_data: str) -> str:
    if model is None:
        raise RuntimeError("Model not initialized")
    payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    if isinstance(payload, list):
        payload = payload[0]

    base_post = load_postprocess_config(_pipeline)
    post = merge_payload_postprocess(payload, base_post)
    preprocess_cfg = load_preprocess_config(_pipeline)

    image = _decode_image(payload)
    image = apply_pil_preprocess(image, preprocess_cfg)
    img_array = np.array(image)

    detections = run_yolo_detection(model, img_array, post)
    return json.dumps(
        {
            "detections": detections,
            "count": len(detections),
            "sahi": post.sahi,
            "ensemble": post.ensemble,
            "tta": post.tta,
        }
    )
