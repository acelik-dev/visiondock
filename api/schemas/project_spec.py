"""VisionDock ProjectSpec v1 — shared contract for UI, API, and future training jobs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TaskType = Literal[
    "classification",
    "multi_label",
    "regression",
    "object_localization",
    "object_detection",
]

DEFAULT_NORMALIZE: dict[str, list[float]] = {
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
}

VALID_TASK_TYPES = frozenset(
    {
        "classification",
        "multi_label",
        "regression",
        "object_localization",
        "object_detection",
    }
)


def _coerce_resize(value: Any, default: str = "224x224") -> str:
    """Normalize LLM or legacy resize values to a WxH string."""
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    if isinstance(value, (int, float)):
        n = int(value)
        return f"{n}x{n}"
    if isinstance(value, dict):
        for key in ("target_size", "size", "resolution", "dims", "image_size"):
            if key in value:
                return _coerce_resize(value[key], default)
        width = value.get("width") or value.get("w")
        height = value.get("height") or value.get("h")
        if width is not None and height is not None:
            return f"{int(width)}x{int(height)}"
        if width is not None:
            n = int(width)
            return f"{n}x{n}"
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            return f"{int(value[0])}x{int(value[1])}"
        if len(value) == 1:
            n = int(value[0])
            return f"{n}x{n}"
    return default


def _coerce_triplet(value: Any, default: list[float]) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except (TypeError, ValueError):
            return list(default)
    if isinstance(value, str) and value.strip():
        parts = [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
        if len(parts) >= 3:
            try:
                return [float(parts[0]), float(parts[1]), float(parts[2])]
            except ValueError:
                return list(default)
    return list(default)


def _coerce_normalize(value: Any) -> dict[str, list[float]]:
    if value is None or value is True:
        return dict(DEFAULT_NORMALIZE)
    if value is False:
        return {"mean": [0.0, 0.0, 0.0], "std": [1.0, 1.0, 1.0]}
    if isinstance(value, dict):
        return {
            "mean": _coerce_triplet(value.get("mean"), DEFAULT_NORMALIZE["mean"]),
            "std": _coerce_triplet(value.get("std"), DEFAULT_NORMALIZE["std"]),
        }
    return dict(DEFAULT_NORMALIZE)


def _coerce_bool(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    # VLMs often return augmentation as a flag map: {mosaic: true, mixup: false, ...}
    if isinstance(value, dict):
        if not value:
            return False
        boolish = []
        for v in value.values():
            if isinstance(v, bool):
                boolish.append(v)
            elif isinstance(v, (int, float)):
                boolish.append(bool(v))
            elif isinstance(v, str):
                lowered = v.strip().lower()
                if lowered in ("1", "true", "yes", "on"):
                    boolish.append(True)
                elif lowered in ("0", "false", "no", "off"):
                    boolish.append(False)
        if boolish:
            return any(boolish)
        return True
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return value


def _coerce_gpu(value: Any, default: str = "NVIDIA T4") -> str:
    """Normalize LLM hardware.gpu (string or nested object) to a display string."""
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    if isinstance(value, dict):
        for key in ("type", "name", "model", "gpu", "sku", "instance"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                text = raw.strip()
                count = value.get("count") or value.get("gpus") or value.get("num")
                mem = value.get("memory_gb") or value.get("vram_gb") or value.get("memory")
                parts = [text]
                if count not in (None, "", 1, "1"):
                    parts.append(f"x{count}")
                if mem not in (None, ""):
                    try:
                        parts.append(f"({int(mem)}GB)")
                    except (TypeError, ValueError):
                        parts.append(f"({mem})")
                return " ".join(parts)
        # Fallback: compact JSON-ish summary
        bits = []
        for key in ("type", "name", "count", "memory_gb", "vram_gb"):
            if key in value and value[key] is not None:
                bits.append(f"{key}={value[key]}")
        return ", ".join(bits) if bits else default
    return default


def _coerce_vram_gb(value: Any, default: int = 16) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(1, int(value))
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else default
    if isinstance(value, dict):
        for key in ("vram_gb", "memory_gb", "memory", "gb"):
            if key in value:
                return _coerce_vram_gb(value[key], default)
    return default


def _coerce_export_format(value: Any) -> list[str]:
    if value is None:
        return ["onnx"]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ["onnx"]
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if item is not None and str(item).strip()]
        return items or ["onnx"]
    return ["onnx"]


def _coerce_classes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    return []


def _normalize_task_token(value: Any) -> str:
    """Lowercase + spaces/hyphens to underscores. No synonym dictionary."""
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _coerce_task_type(value: Any) -> str:
    text = _normalize_task_token(value)
    return text if text in VALID_TASK_TYPES else "classification"


def coerce_known_task_type(value: Any) -> str | None:
    """Accept only the five VLM enum values. Unknown → None."""
    if not value:
        return None
    text = _normalize_task_token(value)
    return text if text in VALID_TASK_TYPES else None


def apply_resolved_task_type(spec: ProjectSpec, task: str | None) -> ProjectSpec:
    """Lock a parsed spec to a VLM-resolved task type."""
    resolved = coerce_known_task_type(task)
    if not resolved or resolved == spec.task_type:
        return spec
    return apply_task_defaults(spec.model_copy(update={"task_type": resolved}))


class TrainingConfigSpec(BaseModel):
    epochs: int = 50
    batch_size: int = 16
    learning_rate: float = 0.001
    image_size: str = "640x640"
    optimizer: str = "AdamW"
    scheduler: str = "cosine"
    early_stopping_patience: int = 10
    validation_split: float = 0.2
    augmentation: bool = True
    mixup: bool = False
    cutmix: bool = False
    label_smoothing: float = 0.0

    @field_validator("image_size", mode="before")
    @classmethod
    def _coerce_image_size(cls, value: Any) -> str:
        return _coerce_resize(value, "640x640")

    @field_validator("augmentation", "mixup", "cutmix", mode="before")
    @classmethod
    def _coerce_training_bools(cls, value: Any) -> Any:
        return _coerce_bool(value)


class PreprocessingSpec(BaseModel):
    resize: str = "640x640"
    normalize: dict = Field(default_factory=lambda: dict(DEFAULT_NORMALIZE))
    grayscale: bool = False
    denoise: bool = False
    contrast_enhancement: bool = False
    auto_orientation: bool = True

    @field_validator("resize", mode="before")
    @classmethod
    def _coerce_resize_field(cls, value: Any) -> str:
        return _coerce_resize(value, "640x640")

    @field_validator("normalize", mode="before")
    @classmethod
    def _coerce_normalize_field(cls, value: Any) -> dict[str, list[float]]:
        return _coerce_normalize(value)

    @field_validator(
        "grayscale",
        "denoise",
        "contrast_enhancement",
        "auto_orientation",
        mode="before",
    )
    @classmethod
    def _coerce_preprocessing_bools(cls, value: Any) -> Any:
        return _coerce_bool(value)


class PostprocessingSpec(BaseModel):
    confidence_threshold: float = 0.5
    nms_iou_threshold: float = 0.5
    tta: bool = False
    ensemble: bool = False
    sahi: bool = False
    sahi_slice_size: int = 640
    sahi_overlap_ratio: float = 0.2
    auto_tune_thresholds: bool = True
    export_format: list[str] = Field(default_factory=lambda: ["onnx"])

    @field_validator("export_format", mode="before")
    @classmethod
    def _coerce_export_format_field(cls, value: Any) -> list[str]:
        return _coerce_export_format(value)

    @field_validator("tta", "ensemble", "sahi", "auto_tune_thresholds", mode="before")
    @classmethod
    def _coerce_postprocessing_bools(cls, value: Any) -> Any:
        return _coerce_bool(value)


class HardwareRequirementsSpec(BaseModel):
    gpu: str = "NVIDIA T4"
    vram_gb: int = 16
    estimated_training_time: str = "4–8 hours"
    estimated_cost: str = "$20–40"

    @field_validator("gpu", mode="before")
    @classmethod
    def _coerce_gpu_field(cls, value: Any) -> str:
        return _coerce_gpu(value)

    @field_validator("vram_gb", mode="before")
    @classmethod
    def _coerce_vram_field(cls, value: Any) -> int:
        return _coerce_vram_gb(value)

    @field_validator("estimated_training_time", "estimated_cost", mode="before")
    @classmethod
    def _coerce_hw_strings(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, (dict, list, tuple)):
            return str(value)
        return value


class ProjectSpec(BaseModel):
    spec_version: str = "1.0"
    project_name: str
    task_type: TaskType
    recommended_model: str
    description: str = ""
    classes: list[str] = Field(default_factory=list)
    target_name: str = ""
    target_unit: str = ""
    estimated_dataset_size: str = "1000–5000 images"
    training_config: TrainingConfigSpec = Field(default_factory=TrainingConfigSpec)
    preprocessing: PreprocessingSpec = Field(default_factory=PreprocessingSpec)
    postprocessing: PostprocessingSpec = Field(default_factory=PostprocessingSpec)
    hardware_requirements: HardwareRequirementsSpec = Field(
        default_factory=HardwareRequirementsSpec
    )

    @field_validator("task_type", mode="before")
    @classmethod
    def _coerce_task_type_field(cls, value: Any) -> str:
        return _coerce_task_type(value)

    @field_validator("classes", mode="before")
    @classmethod
    def _coerce_classes_field(cls, value: Any) -> list[str]:
        return _coerce_classes(value)


def coerce_spec_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw LLM JSON before ProjectSpec validation."""
    out = dict(data)
    out["task_type"] = _coerce_task_type(out.get("task_type"))
    out["classes"] = _coerce_classes(out.get("classes"))

    pre = out.get("preprocessing")
    pre = dict(pre) if isinstance(pre, dict) else {}
    pre["resize"] = _coerce_resize(pre.get("resize"), "640x640")
    pre["normalize"] = _coerce_normalize(pre.get("normalize"))
    for key in ("grayscale", "denoise", "contrast_enhancement", "auto_orientation"):
        if key in pre:
            pre[key] = _coerce_bool(pre[key])
    out["preprocessing"] = pre

    training = out.get("training_config")
    if isinstance(training, dict):
        training = dict(training)
        training["image_size"] = _coerce_resize(training.get("image_size"), pre["resize"])
        for key in ("augmentation", "mixup", "cutmix"):
            if key in training:
                # Nested augmentation maps → master bool; also lift mixup/cutmix flags.
                raw_aug = training.get(key)
                if key == "augmentation" and isinstance(raw_aug, dict):
                    if "mixup" in raw_aug and "mixup" not in training:
                        training["mixup"] = _coerce_bool(raw_aug.get("mixup"))
                    if "cutmix" in raw_aug and "cutmix" not in training:
                        training["cutmix"] = _coerce_bool(raw_aug.get("cutmix"))
                training[key] = _coerce_bool(raw_aug)
        out["training_config"] = training

    post = out.get("postprocessing")
    post = dict(post) if isinstance(post, dict) else {}
    post["export_format"] = _coerce_export_format(post.get("export_format"))
    for key in ("tta", "ensemble", "sahi", "auto_tune_thresholds"):
        if key in post:
            post[key] = _coerce_bool(post[key])
    out["postprocessing"] = post

    hw = out.get("hardware_requirements")
    if isinstance(hw, dict):
        hw = dict(hw)
        # Sometimes VLM puts the whole GPU object at top-level and omits vram_gb.
        gpu_raw = hw.get("gpu")
        hw["gpu"] = _coerce_gpu(gpu_raw)
        if "vram_gb" not in hw and isinstance(gpu_raw, dict):
            hw["vram_gb"] = _coerce_vram_gb(
                gpu_raw.get("memory_gb") or gpu_raw.get("vram_gb") or gpu_raw.get("memory"),
                16,
            )
        else:
            hw["vram_gb"] = _coerce_vram_gb(hw.get("vram_gb"), 16)
        out["hardware_requirements"] = hw

    return out


def parse_project_spec(data: dict[str, Any]) -> ProjectSpec:
    """Coerce LLM output, validate, and apply task-specific defaults."""
    return apply_task_defaults(ProjectSpec.model_validate(coerce_spec_dict(data)))


def apply_task_defaults(spec: ProjectSpec) -> ProjectSpec:
    """Merge task-specific preprocessing/postprocessing defaults (rules + LLM output)."""
    data = spec.model_dump()
    task = _coerce_task_type(data.get("task_type"))
    data["task_type"] = task

    if task == "classification":
        data["preprocessing"]["resize"] = _coerce_resize(
            data["preprocessing"].get("resize"), "224x224"
        )
        data["training_config"]["image_size"] = "224x224"
        if not data.get("recommended_model") or "yolo" in data.get("recommended_model", "").lower():
            data["recommended_model"] = "EfficientNet-B0"
        data["postprocessing"]["nms_iou_threshold"] = 0.0
        data["postprocessing"]["export_format"] = ["onnx", "torchscript"]

    elif task == "multi_label":
        data["preprocessing"]["resize"] = _coerce_resize(
            data["preprocessing"].get("resize"), "224x224"
        )
        data["training_config"]["image_size"] = "224x224"
        if not data.get("recommended_model"):
            data["recommended_model"] = "EfficientNet-B0"
        data["postprocessing"]["nms_iou_threshold"] = 0.0
        data["postprocessing"]["export_format"] = ["onnx", "torchscript"]

    elif task == "regression":
        data["preprocessing"]["resize"] = _coerce_resize(
            data["preprocessing"].get("resize"), "224x224"
        )
        data["training_config"]["image_size"] = "224x224"
        if not data.get("recommended_model"):
            data["recommended_model"] = "EfficientNet-B0"
        data["postprocessing"]["nms_iou_threshold"] = 0.0
        data["postprocessing"]["export_format"] = ["onnx", "torchscript"]
        if not data.get("target_name"):
            data["target_name"] = "target"

    elif task in ("object_localization", "object_detection"):
        data["preprocessing"]["resize"] = _coerce_resize(
            data["preprocessing"].get("resize"), "640x640"
        )
        data["training_config"]["image_size"] = "640x640"
        if not data.get("recommended_model") or "efficient" in data.get("recommended_model", "").lower():
            data["recommended_model"] = "YOLOv8n" if task == "object_localization" else "YOLOv8m"
        data["postprocessing"]["nms_iou_threshold"] = data["postprocessing"].get("nms_iou_threshold") or 0.5
        data["postprocessing"]["export_format"] = ["onnx", "torchscript"]

    return ProjectSpec.model_validate(data)
