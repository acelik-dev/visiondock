"""Shared postprocessing config + detection runners."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class PostprocessConfig:
    confidence_threshold: float = 0.5
    nms_iou_threshold: float = 0.5
    tta: bool = False
    ensemble: bool = False
    sahi: bool = False
    sahi_slice_size: int = 640
    sahi_overlap_ratio: float = 0.2
    auto_tune_thresholds: bool = True

    def to_dict(self) -> dict:
        return {
            "confidence_threshold": self.confidence_threshold,
            "nms_iou_threshold": self.nms_iou_threshold,
            "tta": self.tta,
            "ensemble": self.ensemble,
            "sahi": self.sahi,
            "sahi_slice_size": self.sahi_slice_size,
            "sahi_overlap_ratio": self.sahi_overlap_ratio,
            "auto_tune_thresholds": self.auto_tune_thresholds,
        }


def postprocess_config_from_dict(data: dict | None) -> PostprocessConfig:
    post = data or {}
    return PostprocessConfig(
        confidence_threshold=float(post.get("confidence_threshold", 0.5)),
        nms_iou_threshold=float(post.get("nms_iou_threshold", 0.5)),
        tta=bool(post.get("tta")),
        ensemble=bool(post.get("ensemble")),
        sahi=bool(post.get("sahi")),
        sahi_slice_size=int(post.get("sahi_slice_size", 640)),
        sahi_overlap_ratio=float(post.get("sahi_overlap_ratio", 0.2)),
        auto_tune_thresholds=post.get("auto_tune_thresholds", True) is not False,
    )


def load_postprocess_config(pipeline: dict | None = None) -> PostprocessConfig:
    if pipeline and isinstance(pipeline.get("postprocessing"), dict):
        return postprocess_config_from_dict(pipeline["postprocessing"])
    raw = os.environ.get("PIPELINE_JSON", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data.get("postprocessing"), dict):
                return postprocess_config_from_dict(data["postprocessing"])
        except json.JSONDecodeError:
            pass
    return PostprocessConfig(
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.5")),
        nms_iou_threshold=float(os.getenv("NMS_IOU_THRESHOLD", "0.5")),
        tta=os.getenv("TTA", "").lower() in ("1", "true", "yes"),
        ensemble=os.getenv("ENSEMBLE", "").lower() in ("1", "true", "yes"),
        sahi=os.getenv("SAHI", "").lower() in ("1", "true", "yes"),
        sahi_slice_size=int(os.getenv("SAHI_SLICE_SIZE", "640")),
        sahi_overlap_ratio=float(os.getenv("SAHI_OVERLAP_RATIO", "0.2")),
    )


def merge_payload_postprocess(payload: dict, base: PostprocessConfig) -> PostprocessConfig:
    conf = float(payload.get("confidence", payload.get("confidence_threshold", base.confidence_threshold)))
    iou = float(payload.get("iou", payload.get("nms_iou_threshold", base.nms_iou_threshold)))
    return PostprocessConfig(
        confidence_threshold=conf,
        nms_iou_threshold=iou,
        tta=bool(payload.get("tta", base.tta)),
        ensemble=bool(payload.get("ensemble", base.ensemble)),
        sahi=bool(payload.get("sahi", base.sahi)),
        sahi_slice_size=int(payload.get("sahi_slice_size", base.sahi_slice_size)),
        sahi_overlap_ratio=float(payload.get("sahi_overlap_ratio", base.sahi_overlap_ratio)),
        auto_tune_thresholds=base.auto_tune_thresholds,
    )


def run_yolo_detection(
    model,
    image_array,
    post: PostprocessConfig,
) -> list[dict[str, Any]]:
    if post.ensemble:
        from ensemble_detection import predict_ensemble

        return predict_ensemble(
            model,
            image_array,
            conf=post.confidence_threshold,
            iou=post.nms_iou_threshold,
            tta=post.tta,
        )
    if post.sahi:
        from tiled_detection import predict_tiled

        return predict_tiled(
            model,
            image_array,
            conf=post.confidence_threshold,
            iou=post.nms_iou_threshold,
            tta=post.tta,
            slice_size=post.sahi_slice_size,
            overlap_ratio=post.sahi_overlap_ratio,
        )
    results = model.predict(
        source=image_array,
        conf=post.confidence_threshold,
        iou=post.nms_iou_threshold,
        augment=post.tta,
        verbose=False,
    )
    detections: list[dict[str, Any]] = []
    names = results[0].names or {}
    for box in results[0].boxes or []:
        cls_id = int(box.cls[0])
        detections.append(
            {
                "class_id": cls_id,
                "class_name": names.get(cls_id, str(cls_id)),
                "confidence": float(box.conf[0]),
                "bbox_xyxy": [float(x) for x in box.xyxy[0].tolist()],
            }
        )
    return detections
