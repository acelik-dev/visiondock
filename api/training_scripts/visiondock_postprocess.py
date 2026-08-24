"""Postprocessing config helpers for training jobs."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


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
            "export_format": [
                f.strip()
                for f in os.environ.get("EXPORT_FORMATS", "onnx").split(",")
                if f.strip()
            ],
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
        auto_tune_thresholds=os.getenv("AUTO_TUNE_THRESHOLDS", "1").lower() not in ("0", "false", "no"),
    )
