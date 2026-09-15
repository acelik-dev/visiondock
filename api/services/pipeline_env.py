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


def _normalize_skill_ids(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()]
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if x is not None and str(x).strip()]
    return []


def resolve_pipeline_from_skills(
    *,
    enabled_skills: list[str],
    preprocessing: dict | None = None,
    postprocessing: dict | None = None,
    training_config: dict | None = None,
    skills: list | None = None,
) -> tuple[dict, dict, dict, list[str]]:
    """Expand enabled_skills + default_params into pipeline buckets via registry."""
    from schemas.skills import SkillItem
    from services.skills_store import apply_skills_to_spec_dict, get_skills_store

    pre = dict(preprocessing or {})
    post = dict(postprocessing or {})
    training = dict(training_config or {})
    ids = list(enabled_skills)

    if skills is None:
        try:
            catalog_skills = get_skills_store().list_skills(enabled_only=False)
        except Exception:
            catalog_skills = []
    else:
        catalog_skills = list(skills)

    payload = apply_skills_to_spec_dict(
        {
            "enabled_skills": ids,
            "preprocessing": pre,
            "postprocessing": post,
            "training_config": training,
        },
        [s if isinstance(s, SkillItem) else SkillItem.model_validate(s) for s in catalog_skills],
    )
    return (
        dict(payload.get("preprocessing") or {}),
        dict(payload.get("postprocessing") or {}),
        dict(payload.get("training_config") or {}),
        list(payload.get("enabled_skills") or []),
    )


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
    pre = dict(config.get("preprocessing") or spec.get("preprocessing") or {})
    post = dict(config.get("postprocessing") or spec.get("postprocessing") or {})
    training = dict(
        config.get("training_config")
        or spec.get("training_config")
        or {}
    )
    enabled_skills = _normalize_skill_ids(
        config.get("enabled_skills") if config.get("enabled_skills") is not None else spec.get("enabled_skills")
    )

    # Runtime path: enabled_skills + default_params drive pipeline buckets.
    if enabled_skills:
        try:
            pre, post, training, enabled_skills = resolve_pipeline_from_skills(
                enabled_skills=enabled_skills,
                preprocessing=pre,
                postprocessing=post,
                training_config=training,
            )
        except Exception:
            pass

    pipeline = {
        "preprocessing": pre,
        "postprocessing": post,
        "training_config": training,
        "enabled_skills": list(enabled_skills),
    }
    env = {
        **preprocessing_env_vars(pre, imgsz),
        **postprocessing_env_vars(post),
        "PIPELINE_JSON": json.dumps(pipeline, separators=(",", ":")),
        "ENABLED_SKILLS": ",".join(str(x) for x in enabled_skills),
    }
    # Flatten training flags so azure_ml_service / scripts can read top-level too.
    if training.get("augmentation") is not None:
        env["AUGMENTATION"] = "1" if training.get("augmentation") else "0"
    if training.get("mixup") is not None:
        env["MIXUP_ENABLED"] = "1" if training.get("mixup") else "0"
    if training.get("cutmix") is not None:
        env["CUTMIX_ENABLED"] = "1" if training.get("cutmix") else "0"
    return env


def merge_spec_pipeline_into_config(spec: dict | None, config: dict) -> dict:
    """Ensure training submit config carries skills-resolved pipeline fields."""
    if not spec:
        return config
    merged = dict(config)
    enabled = _normalize_skill_ids(
        merged.get("enabled_skills") if merged.get("enabled_skills") is not None else spec.get("enabled_skills")
    )
    pre = dict(merged.get("preprocessing") or spec.get("preprocessing") or {})
    post = dict(merged.get("postprocessing") or spec.get("postprocessing") or {})
    training = dict(merged.get("training_config") or spec.get("training_config") or {})

    if enabled:
        try:
            pre, post, training, enabled = resolve_pipeline_from_skills(
                enabled_skills=enabled,
                preprocessing=pre,
                postprocessing=post,
                training_config=training,
            )
        except Exception:
            pass

    if pre:
        merged["preprocessing"] = pre
    if post:
        merged["postprocessing"] = post
    if enabled:
        merged["enabled_skills"] = enabled
    if training:
        merged["training_config"] = training
        for key in ("augmentation", "mixup", "cutmix", "image_size"):
            if key in training and key not in merged:
                merged[key] = training[key]
    return merged
