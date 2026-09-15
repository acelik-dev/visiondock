"""Whitelist of skill entrypoints + code-owned apply rules.

Admin / VLM pick skill ids and default_params. Runtime never executes free-form
code; it applies these fixed rules into preprocessing / postprocessing /
training_config, which AML scripts already consume via env vars.
"""

from __future__ import annotations

from typing import Any, Literal

Bucket = Literal["preprocessing", "postprocessing", "training"]

# Declarative apply ops for an entrypoint.
# - value: constant written to bucket[key]
# - from_param: copy params[from_param] → bucket[key]
# - from_params: copy entire params dict → bucket[key]
ApplyOp = dict[str, Any]

ENTRYPOINT_REGISTRY: dict[str, dict[str, Any]] = {
    "visiondock_preprocess.resize": {
        "label": "Resize (WxH)",
        "module": "visiondock_preprocess",
        "symbol": "parse_imgsz",
        "stage": "preprocessing",
        "apply": [{"bucket": "preprocessing", "key": "resize", "from_param": "size"}],
        "detect_keys": ["resize"],
    },
    "visiondock_preprocess.normalize": {
        "label": "Normalize (ImageNet mean/std)",
        "module": "visiondock_preprocess",
        "symbol": "PreprocessConfig",
        "stage": "preprocessing",
        "apply": [{"bucket": "preprocessing", "key": "normalize", "from_params": True}],
        "detect_keys": ["normalize"],
    },
    "visiondock_preprocess.grayscale": {
        "label": "Grayscale",
        "module": "visiondock_preprocess",
        "symbol": "apply_pil_preprocess",
        "stage": "preprocessing",
        "apply": [{"bucket": "preprocessing", "key": "grayscale", "value": True}],
        "detect_keys": ["grayscale"],
    },
    "visiondock_preprocess.denoise": {
        "label": "Denoise (OpenCV)",
        "module": "visiondock_preprocess",
        "symbol": "apply_pil_preprocess",
        "stage": "preprocessing",
        "apply": [{"bucket": "preprocessing", "key": "denoise", "value": True}],
        "detect_keys": ["denoise"],
    },
    "visiondock_preprocess.contrast": {
        "label": "Contrast enhancement",
        "module": "visiondock_preprocess",
        "symbol": "apply_pil_preprocess",
        "stage": "preprocessing",
        "apply": [{"bucket": "preprocessing", "key": "contrast_enhancement", "value": True}],
        "detect_keys": ["contrast_enhancement"],
    },
    "visiondock_preprocess.auto_orientation": {
        "label": "Auto EXIF orientation",
        "module": "visiondock_preprocess",
        "symbol": "apply_pil_preprocess",
        "stage": "preprocessing",
        "apply": [{"bucket": "preprocessing", "key": "auto_orientation", "value": True}],
        "detect_keys": ["auto_orientation"],
    },
    "visiondock_augment.randaugment": {
        "label": "RandAugment / ColorJitter",
        "module": "visiondock_augment",
        "symbol": "build_train_transforms",
        "stage": "augmentation",
        "apply": [{"bucket": "training", "key": "augmentation", "value": True}],
        "detect_keys": ["augmentation"],
    },
    "visiondock_augment.mixup": {
        "label": "MixUp",
        "module": "visiondock_augment",
        "symbol": "mixup",
        "stage": "augmentation",
        "apply": [{"bucket": "training", "key": "mixup", "value": True}],
        "detect_keys": ["mixup"],
    },
    "visiondock_augment.cutmix": {
        "label": "CutMix",
        "module": "visiondock_augment",
        "symbol": "cutmix",
        "stage": "augmentation",
        "apply": [{"bucket": "training", "key": "cutmix", "value": True}],
        "detect_keys": ["cutmix"],
    },
    "visiondock_postprocess.confidence": {
        "label": "Confidence threshold",
        "module": "visiondock_postprocess",
        "symbol": "PostprocessConfig",
        "stage": "postprocessing",
        "apply": [
            {
                "bucket": "postprocessing",
                "key": "confidence_threshold",
                "from_param": "confidence_threshold",
            }
        ],
        "detect_keys": ["confidence_threshold"],
    },
    "visiondock_postprocess.nms": {
        "label": "NMS IoU threshold",
        "module": "visiondock_postprocess",
        "symbol": "PostprocessConfig",
        "stage": "postprocessing",
        "apply": [
            {
                "bucket": "postprocessing",
                "key": "nms_iou_threshold",
                "from_param": "nms_iou_threshold",
            }
        ],
        "detect_keys": ["nms_iou_threshold"],
    },
    "visiondock_postprocess.sahi": {
        "label": "SAHI tiled detection",
        "module": "visiondock_postprocess",
        "symbol": "run_yolo_detection",
        "stage": "postprocessing",
        "apply": [
            {"bucket": "postprocessing", "key": "sahi", "value": True},
            {
                "bucket": "postprocessing",
                "key": "sahi_slice_size",
                "from_param": "sahi_slice_size",
            },
            {
                "bucket": "postprocessing",
                "key": "sahi_overlap_ratio",
                "from_param": "sahi_overlap_ratio",
            },
        ],
        "detect_keys": ["sahi"],
    },
    "visiondock_postprocess.tta": {
        "label": "Test-time augmentation",
        "module": "visiondock_postprocess",
        "symbol": "run_yolo_detection",
        "stage": "postprocessing",
        "apply": [{"bucket": "postprocessing", "key": "tta", "value": True}],
        "detect_keys": ["tta"],
    },
    "visiondock_postprocess.ensemble": {
        "label": "Multi-scale ensemble",
        "module": "visiondock_postprocess",
        "symbol": "run_yolo_detection",
        "stage": "postprocessing",
        "apply": [{"bucket": "postprocessing", "key": "ensemble", "value": True}],
        "detect_keys": ["ensemble"],
    },
    "visiondock_postprocess.export": {
        "label": "Export formats",
        "module": "visiondock_postprocess",
        "symbol": "PostprocessConfig",
        "stage": "postprocessing",
        "apply": [
            {
                "bucket": "postprocessing",
                "key": "export_format",
                "from_param": "export_format",
            }
        ],
        "detect_keys": ["export_format"],
    },
}

# Structural skills always inferred when reverse-mapping old specs.
ALWAYS_ON_SKILL_IDS = frozenset({"pre.resize", "pre.normalize", "post.export"})


def list_entrypoints(*, stage: str | None = None) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key, meta in ENTRYPOINT_REGISTRY.items():
        if stage and meta.get("stage") != stage:
            continue
        items.append(
            {
                "id": key,
                "label": meta["label"],
                "module": meta["module"],
                "symbol": meta["symbol"],
                "stage": meta["stage"],
            }
        )
    return items


def is_known_entrypoint(entrypoint: str) -> bool:
    return entrypoint in ENTRYPOINT_REGISTRY


def entrypoint_meta(entrypoint: str) -> dict[str, Any] | None:
    return ENTRYPOINT_REGISTRY.get(entrypoint)


def apply_entrypoint(
    entrypoint: str,
    params: dict[str, Any] | None,
    *,
    preprocessing: dict[str, Any],
    postprocessing: dict[str, Any],
    training: dict[str, Any],
) -> None:
    """Mutate pipeline buckets according to code-owned rules for this entrypoint."""
    meta = ENTRYPOINT_REGISTRY.get(entrypoint)
    if not meta:
        return
    params = dict(params or {})
    buckets: dict[str, dict[str, Any]] = {
        "preprocessing": preprocessing,
        "postprocessing": postprocessing,
        "training": training,
    }
    for op in meta.get("apply") or []:
        bucket_name = op.get("bucket")
        key = op.get("key")
        if not bucket_name or not key or bucket_name not in buckets:
            continue
        target = buckets[bucket_name]
        if "value" in op:
            target[key] = op["value"]
        elif op.get("from_params"):
            target[key] = dict(params)
        elif "from_param" in op:
            pname = op["from_param"]
            if pname in params:
                target[key] = params[pname]


def entrypoint_matches_pipeline(
    entrypoint: str,
    *,
    preprocessing: dict[str, Any],
    postprocessing: dict[str, Any],
    training: dict[str, Any],
) -> bool:
    """True when pipeline flags look like this entrypoint was enabled."""
    meta = ENTRYPOINT_REGISTRY.get(entrypoint)
    if not meta:
        return False
    stage = meta.get("stage")
    detect = meta.get("detect_keys") or []
    if stage == "postprocessing":
        bucket = postprocessing
    elif stage == "augmentation":
        bucket = training
    else:
        bucket = preprocessing
    for key in detect:
        if key not in bucket:
            continue
        val = bucket.get(key)
        if val is True:
            return True
        if isinstance(val, (int, float, str, list, dict)) and val not in (False, None, "", []):
            return True
    return False
