"""Sample dataset images and tune pipeline settings with the VLM."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import random
import threading
import zipfile
from typing import Any

from schemas.project_spec import parse_project_spec
from services.project_store import ProjectStore
from services.vlm_client import (
    flush_langfuse,
    get_vlm_client,
    vlm_model,
    vlm_token_kwargs,
    vlm_trace_kwargs,
)

logger = logging.getLogger(__name__)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_IMAGES = 6
MAX_BYTES_PER_IMAGE = 3_500_000

_tune_locks: dict[str, threading.Lock] = {}
_tune_locks_guard = threading.Lock()


def _mime_for_key(key: str) -> str:
    ext = "." + key.lower().rsplit(".", 1)[-1] if "." in key else ""
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def _to_data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _is_image_path(path: str) -> bool:
    ext = "." + path.lower().rsplit(".", 1)[-1] if "." in path else ""
    return ext in IMAGE_EXT


def _sample_from_zip(raw: bytes, max_n: int) -> list[str]:
    urls: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if _is_image_path(n) and not n.endswith("/")]
            random.shuffle(names)
            for name in names[:max_n]:
                data = zf.read(name)
                if len(data) > MAX_BYTES_PER_IMAGE:
                    continue
                urls.append(_to_data_url(data, _mime_for_key(name)))
    except zipfile.BadZipFile:
        pass
    return urls


def _is_marketplace_dataset(ds: dict[str, Any]) -> bool:
    return (
        ds.get("source") == "marketplace"
        and ds.get("import_status") == "completed"
        and bool(ds.get("validated"))
    )


def _sample_from_prefix(store, prefix: str, max_n: int) -> list[str]:
    if not prefix:
        return []
    norm = prefix if prefix.endswith("/") else f"{prefix.rstrip('/')}/"
    keys = [
        k
        for k in store.list_prefix(norm)
        if _is_image_path(k) and "/previews/" not in k.lower()
    ]
    random.shuffle(keys)
    urls: list[str] = []
    for key in keys[: max_n * 2]:
        data = store.read_bytes(key)
        if data and len(data) <= MAX_BYTES_PER_IMAGE:
            urls.append(_to_data_url(data, _mime_for_key(key)))
        if len(urls) >= max_n:
            break
    return urls


def _sample_marketplace_images(project_store: ProjectStore, meta: dict[str, Any], max_n: int) -> list[str]:
    ds = meta.get("dataset") or {}
    storage_key = str(ds.get("storage_key") or "")
    urls: list[str] = []

    if storage_key.lower().endswith(".zip"):
        raw = project_store.store.read_bytes(storage_key)
        if raw:
            urls = _sample_from_zip(raw, max_n)
    elif storage_key:
        urls = _sample_from_prefix(project_store.store, storage_key, max_n)

    item_id = ds.get("marketplace_item_id")
    if len(urls) < 1 and item_id:
        try:
            from services.marketplace_store import get_marketplace_store

            mp = get_marketplace_store()
            item = mp.get_dataset(str(item_id))
            if item:
                mp.ensure_dataset_previews(item)
                for fname in mp.list_dataset_preview_names(str(item_id))[:max_n]:
                    preview = mp.read_dataset_preview(str(item_id), fname)
                    if not preview:
                        continue
                    data, content_type = preview
                    if len(data) <= MAX_BYTES_PER_IMAGE:
                        urls.append(_to_data_url(data, content_type or "image/jpeg"))
        except Exception as exc:
            logger.debug("Marketplace preview fallback failed: %s", exc)

    return urls[:max_n]


def _dataset_fingerprint(meta: dict[str, Any]) -> str:
    ds = meta.get("dataset") or {}
    return "|".join(
        str(ds.get(k, ""))
        for k in (
            "source",
            "marketplace_item_id",
            "mode",
            "file_name",
            "size_bytes",
            "validated",
            "storage_key",
        )
    )


def sample_dataset_images(project_store: ProjectStore, project_id: str, max_n: int = MAX_IMAGES) -> list[str]:
    meta = project_store.get_meta(project_id)
    if meta is None:
        return []

    spec = project_store.load_spec(project_id) or {}
    task = str(spec.get("task_type") or meta.get("detected_task") or "classification")
    ds = meta.get("dataset") or {}
    mode = ds.get("mode") or task
    urls: list[str] = []

    if _is_marketplace_dataset(ds):
        urls = _sample_marketplace_images(project_store, meta, max_n)
        if urls:
            return urls

    if mode == "classification" or task == "classification":
        prefix = f"projects/{project_id}/datasets/classification/"
        keys = [k for k in project_store.store.list_prefix(prefix) if _is_image_path(k)]
        random.shuffle(keys)
        for key in keys[:max_n]:
            data = project_store.store.read_bytes(key)
            if data and len(data) <= MAX_BYTES_PER_IMAGE:
                urls.append(_to_data_url(data, _mime_for_key(key)))

    elif mode == "multi_label":
        prefix = f"projects/{project_id}/datasets/multi_label/images/"
        keys = [k for k in project_store.store.list_prefix(prefix) if _is_image_path(k)]
        random.shuffle(keys)
        for key in keys[:max_n]:
            data = project_store.store.read_bytes(key)
            if data and len(data) <= MAX_BYTES_PER_IMAGE:
                urls.append(_to_data_url(data, _mime_for_key(key)))

    elif mode == "regression":
        prefix = f"projects/{project_id}/datasets/regression/images/"
        keys = [k for k in project_store.store.list_prefix(prefix) if _is_image_path(k)]
        random.shuffle(keys)
        for key in keys[:max_n]:
            data = project_store.store.read_bytes(key)
            if data and len(data) <= MAX_BYTES_PER_IMAGE:
                urls.append(_to_data_url(data, _mime_for_key(key)))

    elif task in ("object_detection", "object_localization") or ds.get("format") in ("yolo", "coco", "voc"):
        raw = project_store.read_annotated_dataset(project_id)
        if raw:
            urls = _sample_from_zip(raw, max_n)

    if len(urls) < 2:
        raw = project_store.read_dataset(project_id)
        if raw:
            urls = _sample_from_zip(raw, max_n)

    if len(urls) < 1:
        for sample_id in project_store.list_samples(project_id):
            key = f"projects/{project_id}/samples/{sample_id}"
            data = project_store.store.read_bytes(key)
            if data and len(data) <= MAX_BYTES_PER_IMAGE:
                urls.append(_to_data_url(data, _mime_for_key(key)))
            if len(urls) >= max_n:
                break

    return urls[:max_n]


PIPELINE_PROMPT = """You are configuring an ML training pipeline for VisionDock based on ACTUAL dataset images.

Given the task type and images, return ONLY JSON with these keys:
{
  "training_config": {
    "epochs": int,
    "batch_size": int,
    "learning_rate": float,
    "image_size": "WxH string",
    "early_stopping_patience": int,
    "augmentation": bool,
    "mixup": bool,
    "cutmix": bool,
    "label_smoothing": float
  },
  "preprocessing": {
    "resize": "WxH",
    "grayscale": bool,
    "denoise": bool,
    "contrast_enhancement": bool,
    "auto_orientation": bool
  },
  "postprocessing": {
    "confidence_threshold": float,
    "nms_iou_threshold": float,
    "tta": bool,
    "ensemble": bool,
    "sahi": bool,
    "sahi_slice_size": int,
    "sahi_overlap_ratio": float,
    "auto_tune_thresholds": bool
  },
  "rationale": "one short sentence for the user"
}

Rules:
- classification/multi_label/regression: image_size and resize 224x224 unless images are very high-res text/detail (then 384x384).
- object_detection/localization: image_size and resize 640x640; use 1280x1280 only if objects are tiny in large frames.
- Enable sahi=true when objects are small relative to image area (aerial, medical, wide industrial scenes).
- Enable denoise/contrast only if images look noisy, dark, or low-contrast.
- grayscale=true only if images are already mono or color is irrelevant.
- mixup/cutmix: classification only; enable for >=3 classes and varied scenes.
- epochs: 50-100 detection, 30-50 classification depending on dataset complexity visible.
- tta: enable for difficult detection scenes; off for simple uniform scenes.
- ensemble: enable for detection when scale variation is high (same object appears at very different sizes); mutually exclusive with sahi in practice — prefer sahi for tiny objects in large frames, ensemble for mixed scales.
- auto_tune_thresholds: true for detection tasks.
- Do not change task_type or classes."""


def _tune_lock_for(project_id: str) -> threading.Lock:
    with _tune_locks_guard:
        return _tune_locks.setdefault(project_id, threading.Lock())


def tune_pipeline_from_dataset(project_id: str, *, force: bool = False) -> dict[str, Any]:
    # The config page can fire several tunes at once; serialize per project so the
    # later callers hit the stored fingerprint instead of paying for another VLM run.
    with _tune_lock_for(project_id):
        return _tune_pipeline_from_dataset(project_id, force=force)


def _tune_pipeline_from_dataset(project_id: str, *, force: bool = False) -> dict[str, Any]:
    store = ProjectStore()
    meta = store.get_meta(project_id)
    if meta is None:
        raise KeyError(project_id)

    spec_dict = store.load_spec(project_id)
    if not spec_dict:
        raise ValueError("Generate project config before tuning pipeline")

    fingerprint = _dataset_fingerprint(meta)
    if not force and meta.get("pipeline_tune_fingerprint") == fingerprint:
        return {
            "success": True,
            "cached": True,
            "spec": spec_dict,
            "rationale": meta.get("pipeline_tune_rationale"),
        }

    images = sample_dataset_images(store, project_id)
    if not images:
        raise ValueError(
            "Upload a dataset, pick one from the Dataset Library, or add sample images before auto-configuring the pipeline"
        )

    client = get_vlm_client()
    if client is None:
        raise RuntimeError("VLM_API_KEY is not configured")

    task = spec_dict.get("task_type", "classification")
    ds = meta.get("dataset") or {}
    context = (
        f"{PIPELINE_PROMPT}\n\n"
        f"task_type: {task}\n"
        f"recommended_model: {spec_dict.get('recommended_model')}\n"
        f"classes: {spec_dict.get('classes')}\n"
        f"images_provided: {len(images)}\n"
    )
    if ds.get("source") == "marketplace":
        context += (
            f"dataset_source: marketplace\n"
            f"marketplace_name: {ds.get('marketplace_name')}\n"
            f"marketplace_item_id: {ds.get('marketplace_item_id')}\n"
        )

    user_content: list[dict[str, Any]] = [{"type": "text", "text": context}]
    for url in images:
        user_content.append({"type": "image_url", "image_url": {"url": url}})

    try:
        completion = client.chat.completions.create(
            model=vlm_model(),
            messages=[
                {
                    "role": "system",
                    "content": "Return valid JSON only. Tune pipeline from visual analysis.",
                },
                {"role": "user", "content": user_content},
            ],
            **vlm_token_kwargs(2500),
            response_format={"type": "json_object"},
            **vlm_trace_kwargs(
                name="vlm-pipeline-tune",
                project_id=project_id,
                tags=["vlm", "pipeline-tune"],
                metadata={"task_type": task, "image_count": len(images)},
            ),
        )

        raw = json.loads(completion.choices[0].message.content or "{}")
        rationale = str(raw.pop("rationale", "") or "")

        merged = dict(spec_dict)
        if isinstance(raw.get("training_config"), dict):
            merged["training_config"] = {**(merged.get("training_config") or {}), **raw["training_config"]}
        if isinstance(raw.get("preprocessing"), dict):
            merged["preprocessing"] = {**(merged.get("preprocessing") or {}), **raw["preprocessing"]}
        if isinstance(raw.get("postprocessing"), dict):
            merged["postprocessing"] = {**(merged.get("postprocessing") or {}), **raw["postprocessing"]}

        spec = parse_project_spec(merged)
        store.save_spec(project_id, spec)
        store.update_meta(
            project_id,
            {
                "pipeline_tune_fingerprint": fingerprint,
                "pipeline_tune_rationale": rationale,
                "pipeline_tuned_at": __import__("datetime").datetime.utcnow().isoformat(),
            },
        )

        return {
            "success": True,
            "cached": False,
            "spec": spec.model_dump(),
            "rationale": rationale,
            "image_count": len(images),
        }
    finally:
        flush_langfuse()
