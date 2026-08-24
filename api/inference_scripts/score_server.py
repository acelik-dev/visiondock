"""Lightweight edge HTTP server for local Docker inference."""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from PIL import Image
from ultralytics import YOLO

from visiondock_postprocess import load_postprocess_config, merge_payload_postprocess, run_yolo_detection
from visiondock_preprocess import apply_pil_preprocess, load_preprocess_config

app = FastAPI(title="VisionDock Edge Inference")

_model = None
_api_key = os.getenv("VISIONDOCK_API_KEY", "")
_pipeline: dict | None = None


def _load_pipeline() -> dict | None:
    for name in ("model/model.json", "model.json"):
        path = Path(name)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("pipeline"), dict):
                return data["pipeline"]
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _load_model() -> YOLO:
    global _model, _pipeline
    if _model is not None:
        return _model
    _pipeline = _load_pipeline()
    model_path = os.getenv("MODEL_PATH", "/app/model/best.onnx")
    if not Path(model_path).exists():
        pt = Path("/app/model/best.pt")
        model_path = str(pt) if pt.exists() else model_path
    _model = YOLO(model_path)
    return _model


def _check_key(key: str | None) -> None:
    if _api_key and key != _api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
async def predict(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_key(x_api_key)
    raw = await file.read()
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    model = _load_model()
    post = load_postprocess_config(_pipeline)
    preprocess_cfg = load_preprocess_config(_pipeline)
    image = apply_pil_preprocess(image, preprocess_cfg)
    detections = run_yolo_detection(model, np.array(image), post)
    return {"detections": detections, "count": len(detections)}


@app.post("/predict/json")
async def predict_json(payload: dict, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    _check_key(x_api_key)
    b64 = payload.get("image_base64")
    if not b64:
        raise HTTPException(status_code=400, detail="image_base64 required")
    image = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    model = _load_model()
    base_post = load_postprocess_config(_pipeline)
    post = merge_payload_postprocess(payload, base_post)
    preprocess_cfg = load_preprocess_config(_pipeline)
    image = apply_pil_preprocess(image, preprocess_cfg)
    detections = run_yolo_detection(model, np.array(image), post)
    return {"detections": detections, "count": len(detections)}
