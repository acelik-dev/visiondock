"""Shared PIL + env preprocessing used in training and inference."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass
class PreprocessConfig:
    imgsz: int = 224
    grayscale: bool = False
    denoise: bool = False
    contrast_enhancement: bool = False
    auto_orientation: bool = True
    normalize_mean: tuple[float, float, float] = (0.485, 0.456, 0.406)
    normalize_std: tuple[float, float, float] = (0.229, 0.224, 0.225)

    def active_pil_steps(self) -> bool:
        return any(
            [
                self.grayscale,
                self.denoise,
                self.contrast_enhancement,
                self.auto_orientation,
            ]
        )

    def to_dict(self) -> dict:
        return {
            "resize": f"{self.imgsz}x{self.imgsz}",
            "grayscale": self.grayscale,
            "denoise": self.denoise,
            "contrast_enhancement": self.contrast_enhancement,
            "auto_orientation": self.auto_orientation,
            "normalize": {
                "mean": list(self.normalize_mean),
                "std": list(self.normalize_std),
            },
        }


def env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key) or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return default


def parse_imgsz(value: str | int | None, default: int = 224) -> int:
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


def _parse_norm_triplet(raw: str | None, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if not raw:
        return default
    try:
        parts = tuple(float(x.strip()) for x in raw.split(","))
        if len(parts) == 3:
            return parts
    except ValueError:
        pass
    return default


def preprocess_config_from_env() -> PreprocessConfig:
    resize = os.environ.get("PREPROCESS_RESIZE") or os.environ.get("IMGSZ", "224")
    return PreprocessConfig(
        imgsz=parse_imgsz(resize, parse_imgsz(os.environ.get("IMGSZ"), 224)),
        grayscale=env_bool("PREPROCESS_GRAYSCALE"),
        denoise=env_bool("PREPROCESS_DENOISE"),
        contrast_enhancement=env_bool("PREPROCESS_CONTRAST"),
        auto_orientation=env_bool("PREPROCESS_AUTO_ORIENT", True),
        normalize_mean=_parse_norm_triplet(
            os.environ.get("NORMALIZE_MEAN"), (0.485, 0.456, 0.406)
        ),
        normalize_std=_parse_norm_triplet(
            os.environ.get("NORMALIZE_STD"), (0.229, 0.224, 0.225)
        ),
    )


def preprocess_config_from_dict(data: dict | None) -> PreprocessConfig:
    pre = data or {}
    norm = pre.get("normalize") or {}
    mean = norm.get("mean", [0.485, 0.456, 0.406])
    std = norm.get("std", [0.229, 0.224, 0.225])
    try:
        mean_t = tuple(float(x) for x in mean[:3])
        std_t = tuple(float(x) for x in std[:3])
    except (TypeError, ValueError):
        mean_t = (0.485, 0.456, 0.406)
        std_t = (0.229, 0.224, 0.225)
    if len(mean_t) != 3:
        mean_t = (0.485, 0.456, 0.406)
    if len(std_t) != 3:
        std_t = (0.229, 0.224, 0.225)
    return PreprocessConfig(
        imgsz=parse_imgsz(pre.get("resize"), 224),
        grayscale=bool(pre.get("grayscale")),
        denoise=bool(pre.get("denoise")),
        contrast_enhancement=bool(pre.get("contrast_enhancement")),
        auto_orientation=pre.get("auto_orientation", True) is not False,
        normalize_mean=mean_t,
        normalize_std=std_t,
    )


def load_preprocess_config(pipeline: dict | None = None) -> PreprocessConfig:
    if pipeline and isinstance(pipeline.get("preprocessing"), dict):
        return preprocess_config_from_dict(pipeline["preprocessing"])
    raw = os.environ.get("PIPELINE_JSON", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data.get("preprocessing"), dict):
                return preprocess_config_from_dict(data["preprocessing"])
        except json.JSONDecodeError:
            pass
    return preprocess_config_from_env()


def apply_pil_preprocess(image: Image.Image, config: PreprocessConfig) -> Image.Image:
    img = image
    if config.auto_orientation:
        img = ImageOps.exif_transpose(img)
    if config.grayscale:
        img = img.convert("L").convert("RGB")
    else:
        img = img.convert("RGB")
    if config.denoise:
        try:
            import cv2
            import numpy as np

            arr = np.array(img)
            arr = cv2.fastNlMeansDenoisingColored(arr, None, 10, 10, 7, 21)
            img = Image.fromarray(arr)
        except Exception:
            pass
    if config.contrast_enhancement:
        img = ImageEnhance.Contrast(img).enhance(1.35)
        img = ImageEnhance.Brightness(img).enhance(1.05)
    return img


def _iter_image_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXT:
            files.append(path)
    return files


def preprocess_image_tree(src_root: Path, dst_root: Path, config: PreprocessConfig) -> int:
    """Write preprocessed copies preserving relative paths; returns image count."""
    count = 0
    for src in _iter_image_files(src_root):
        rel = src.relative_to(src_root)
        dest = dst_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            out = apply_pil_preprocess(im, config)
            out.save(dest, quality=95)
        count += 1
    return count


def preprocess_yolo_dataset(data_yaml: Path, config: PreprocessConfig) -> Path:
    """Apply PIL preprocessing to YOLO dataset images when any flag is enabled."""
    if not config.active_pil_steps():
        return data_yaml

    import yaml

    with data_yaml.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    root = Path(cfg.get("path") or data_yaml.parent)
    if not root.is_absolute():
        root = (data_yaml.parent / root).resolve()

    processed_root = root.parent / f"{root.name}_preprocessed"
    if processed_root.exists():
        import shutil

        shutil.rmtree(processed_root)
    processed_root.mkdir(parents=True, exist_ok=True)

    count = preprocess_image_tree(root, processed_root, config)
    print(f"Preprocessed {count} YOLO images into {processed_root}", flush=True)

    new_cfg = dict(cfg)
    new_cfg["path"] = str(processed_root)
    for key in ("train", "val", "test"):
        if key in new_cfg and isinstance(new_cfg[key], str):
            rel = Path(new_cfg[key])
            if not rel.is_absolute():
                new_cfg[key] = str(processed_root / rel.name)

    out_yaml = data_yaml.parent / "data_preprocessed.yaml"
    out_yaml.write_text(yaml.dump(new_cfg, default_flow_style=False), encoding="utf-8")
    return out_yaml


def preprocessing_env_vars(pre: dict | None, imgsz: int) -> dict[str, str]:
    cfg = preprocess_config_from_dict(pre or {})
    if not (pre or {}).get("resize"):
        cfg.imgsz = imgsz
    return {
        "PREPROCESS_RESIZE": f"{cfg.imgsz}x{cfg.imgsz}",
        "PREPROCESS_GRAYSCALE": "1" if cfg.grayscale else "0",
        "PREPROCESS_DENOISE": "1" if cfg.denoise else "0",
        "PREPROCESS_CONTRAST": "1" if cfg.contrast_enhancement else "0",
        "PREPROCESS_AUTO_ORIENT": "1" if cfg.auto_orientation else "0",
        "NORMALIZE_MEAN": ",".join(str(x) for x in cfg.normalize_mean),
        "NORMALIZE_STD": ",".join(str(x) for x in cfg.normalize_std),
    }


def export_formats_from_env() -> list[str]:
    raw = os.environ.get("EXPORT_FORMATS", "onnx")
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return parts or ["onnx"]
