"""Build AML environment variables from ProjectSpec preprocessing/postprocessing."""
from __future__ import annotations

import json
from typing import Any


def _parse_imgsz(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    text = str(value).lower().replace(" ", "")
    head = text.split("x")[0]
    try:
        return max(32, int(head))
    except ValueError:
        return default


def preprocessing_env_vars(pre: dict | None, imgsz: int) -> dict[str, str]:
    pre = pre or {}
    norm = pre.get("normalize") or {}
    mean = norm.get("mean", [0.485, 0.456, 0.406])
    std = norm.get("std", [0.229, 0.224, 0.225])
    resize_imgsz = _parse_imgsz(pre.get("resize"), imgsz)
    return {
        "PREPROCESS_RESIZE": f"{resize_imgsz}x{resize_imgsz}",
        "PREPROCESS_GRAYSCALE": "1" if pre.get("grayscale") else "0",
        "PREPROCESS_DENOISE": "1" if pre.get("denoise") else "0",
        "PREPROCESS_CONTRAST": "1" if pre.get("contrast_enhancement") else "0",
        "PREPROCESS_AUTO_ORIENT": "1" if pre.get("auto_orientation", True) else "0",
        "NORMALIZE_MEAN": ",".join(str(float(x)) for x in mean[:3]),
        "NORMALIZE_STD": ",".join(str(float(x)) for x in std[:3]),
    }


def postprocessing_env_vars(post: dict | None) -> dict[str, str]:
    post = post or {}
    export_formats = post.get("export_format") or ["onnx"]
    if isinstance(export_formats, str):
        export_formats = [export_formats]
    return {
        "CONFIDENCE_THRESHOLD": str(post.get("confidence_threshold", 0.5)),
        "NMS_IOU_THRESHOLD": str(post.get("nms_iou_threshold", 0.5)),
        "TTA": "1" if post.get("tta") else "0",
        "ENSEMBLE": "1" if post.get("ensemble") else "0",
        "SAHI": "1" if post.get("sahi") else "0",
        "SAHI_SLICE_SIZE": str(post.get("sahi_slice_size", 640)),
        "SAHI_OVERLAP_RATIO": str(post.get("sahi_overlap_ratio", 0.2)),
        "AUTO_TUNE_THRESHOLDS": "1" if post.get("auto_tune_thresholds", True) else "0",
        "EXPORT_FORMATS": ",".join(str(f).lower() for f in export_formats),
    }


def pipeline_env_from_spec(spec: dict | None, config: dict | None, imgsz: int) -> dict[str, str]:
    spec = spec or {}
    config = config or {}
    pre = config.get("preprocessing") or spec.get("preprocessing") or {}
    post = config.get("postprocessing") or spec.get("postprocessing") or {}
    pipeline = {
        "preprocessing": pre,
        "postprocessing": post,
    }
    env = {
        **preprocessing_env_vars(pre, imgsz),
        **postprocessing_env_vars(post),
        "PIPELINE_JSON": json.dumps(pipeline, separators=(",", ":")),
    }
    return env


def merge_spec_pipeline_into_config(spec: dict | None, config: dict) -> dict:
    """Ensure training submit config carries spec preprocessing/postprocessing."""
    if not spec:
        return config
    merged = dict(config)
    if spec.get("preprocessing") and "preprocessing" not in merged:
        merged["preprocessing"] = spec["preprocessing"]
    if spec.get("postprocessing") and "postprocessing" not in merged:
        merged["postprocessing"] = spec["postprocessing"]
    if spec.get("training_config"):
        tc = dict(spec["training_config"])
        for key in ("image_size",):
            if key in tc and key not in merged:
                merged[key] = tc[key]
    return merged
