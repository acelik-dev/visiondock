"""Read/write skills catalog from blob storage (marketplace-style)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from schemas.skills import (
    SkillItem,
    SkillsCatalog,
    SkillUpsertBody,
    normalize_task_types,
)
from services.skill_registry import (
    ALWAYS_ON_SKILL_IDS,
    apply_entrypoint,
    entrypoint_matches_pipeline,
    is_known_entrypoint,
)
from storage.blob_store import BlobStore, get_blob_store

logger = logging.getLogger("visiondock.skills")

CATALOG_KEY = "skills/catalog.json"
_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")

_catalog_cache: tuple[str | None, SkillsCatalog] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "skills" / "catalog.json"


def default_seed_skills() -> list[dict]:
    """Seed from current generate-config preprocess/postprocess contract."""
    ts = _now()
    return [
        {
            "id": "pre.resize",
            "name": "Resize",
            "description": (
                "Resize every image to a fixed WxH string (e.g. \"224x224\" or \"640x640\"). "
                "classification/multi_label/regression default 224x224; detection/localization 640x640. "
                "MUST be a string, NOT an object."
            ),
            "stage": "preprocessing",
            "task_types": ["*"],
            "entrypoint": "visiondock_preprocess.resize",
            "params_schema": {"size": {"type": "string", "example": "224x224"}},
            "default_params": {"size": "224x224"},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "pre.normalize",
            "name": "Normalize",
            "description": (
                "ImageNet-style normalize. Must be an object "
                '{"mean":[0.485,0.456,0.406],"std":[0.229,0.224,0.225]} — NOT true/false.'
            ),
            "stage": "preprocessing",
            "task_types": ["*"],
            "entrypoint": "visiondock_preprocess.normalize",
            "params_schema": {
                "mean": {"type": "array"},
                "std": {"type": "array"},
            },
            "default_params": {
                "mean": [0.485, 0.456, 0.406],
                "std": [0.229, 0.224, 0.225],
            },
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "pre.grayscale",
            "name": "Grayscale",
            "description": "Convert images to grayscale before training/inference when color is irrelevant (e.g. X-ray, documents).",
            "stage": "preprocessing",
            "task_types": ["*"],
            "entrypoint": "visiondock_preprocess.grayscale",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "pre.denoise",
            "name": "Denoise",
            "description": "OpenCV denoise for noisy industrial cameras. Enable when images are grainy.",
            "stage": "preprocessing",
            "task_types": ["*"],
            "entrypoint": "visiondock_preprocess.denoise",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "pre.contrast",
            "name": "Contrast enhancement",
            "description": "Boost local contrast for low-light or flat scenes.",
            "stage": "preprocessing",
            "task_types": ["*"],
            "entrypoint": "visiondock_preprocess.contrast",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "pre.auto_orientation",
            "name": "Auto orientation",
            "description": "Apply EXIF orientation so upright photos stay upright. Usually leave enabled.",
            "stage": "preprocessing",
            "task_types": ["*"],
            "entrypoint": "visiondock_preprocess.auto_orientation",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "aug.randaugment",
            "name": "Augmentation",
            "description": "Training-time RandAugment / ColorJitter. Boolean on training_config.augmentation.",
            "stage": "augmentation",
            "task_types": ["classification", "multi_label", "regression"],
            "entrypoint": "visiondock_augment.randaugment",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "aug.mixup",
            "name": "MixUp",
            "description": "MixUp augmentation for classification-style tasks. Boolean training_config.mixup.",
            "stage": "augmentation",
            "task_types": ["classification", "multi_label"],
            "entrypoint": "visiondock_augment.mixup",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "aug.cutmix",
            "name": "CutMix",
            "description": "CutMix augmentation. Boolean training_config.cutmix.",
            "stage": "augmentation",
            "task_types": ["classification", "multi_label"],
            "entrypoint": "visiondock_augment.cutmix",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "post.confidence",
            "name": "Confidence threshold",
            "description": "Drop detections below this score (0–1). Typical 0.25–0.5 for detection.",
            "stage": "postprocessing",
            "task_types": ["object_detection", "object_localization"],
            "entrypoint": "visiondock_postprocess.confidence",
            "params_schema": {"confidence_threshold": {"type": "number"}},
            "default_params": {"confidence_threshold": 0.5},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "post.nms",
            "name": "NMS IoU",
            "description": "Non-max suppression IoU. Detection ~0.5; classification must use 0.0.",
            "stage": "postprocessing",
            "task_types": ["object_detection", "object_localization"],
            "entrypoint": "visiondock_postprocess.nms",
            "params_schema": {"nms_iou_threshold": {"type": "number"}},
            "default_params": {"nms_iou_threshold": 0.5},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "post.sahi",
            "name": "SAHI tiled detection",
            "description": "Slice large images into overlapping tiles for small-object detection. Use for high-res industrial scenes.",
            "stage": "postprocessing",
            "task_types": ["object_detection"],
            "entrypoint": "visiondock_postprocess.sahi",
            "params_schema": {
                "sahi_slice_size": {"type": "integer"},
                "sahi_overlap_ratio": {"type": "number"},
            },
            "default_params": {"sahi_slice_size": 640, "sahi_overlap_ratio": 0.2},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "post.tta",
            "name": "Test-time augmentation",
            "description": "Average predictions over flips/scales at inference. Slower, slightly more robust.",
            "stage": "postprocessing",
            "task_types": ["object_detection", "object_localization", "classification"],
            "entrypoint": "visiondock_postprocess.tta",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "post.ensemble",
            "name": "Multi-scale ensemble",
            "description": "Run detection at multiple scales and merge boxes.",
            "stage": "postprocessing",
            "task_types": ["object_detection"],
            "entrypoint": "visiondock_postprocess.ensemble",
            "default_params": {},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
        {
            "id": "post.export",
            "name": "Export formats",
            "description": 'Model export targets. Must be an array like ["onnx","torchscript"], NOT a single string.',
            "stage": "postprocessing",
            "task_types": ["*"],
            "entrypoint": "visiondock_postprocess.export",
            "params_schema": {"export_format": {"type": "array"}},
            "default_params": {"export_format": ["onnx"]},
            "enabled": True,
            "version": 1,
            "updated_at": ts,
        },
    ]


def apply_skills_to_spec_dict(data: dict, skills: list[SkillItem]) -> dict:
    """Apply enabled_skills + default_params via code registry into pipeline buckets."""
    out = dict(data)
    pre = dict(out.get("preprocessing") or {}) if isinstance(out.get("preprocessing"), dict) else {}
    post = dict(out.get("postprocessing") or {}) if isinstance(out.get("postprocessing"), dict) else {}
    training = dict(out.get("training_config") or {}) if isinstance(out.get("training_config"), dict) else {}
    enabled_ids = [str(x) for x in (out.get("enabled_skills") or []) if str(x).strip()]
    by_id = {s.id: s for s in skills if s.enabled}

    for sid in enabled_ids:
        skill = by_id.get(sid)
        if skill is None:
            continue
        apply_entrypoint(
            skill.entrypoint,
            dict(skill.default_params or {}),
            preprocessing=pre,
            postprocessing=post,
            training=training,
        )

    out["preprocessing"] = pre
    out["postprocessing"] = post
    if training:
        out["training_config"] = training
    # Only drop unknown ids when we have a catalog to validate against.
    if by_id:
        out["enabled_skills"] = [sid for sid in enabled_ids if sid in by_id]
    else:
        out["enabled_skills"] = enabled_ids
    return out


def skills_from_legacy_flags(data: dict, skills: list[SkillItem]) -> list[str]:
    """Infer enabled_skills from pipeline buckets when VLM omitted the list."""
    pre = data.get("preprocessing") if isinstance(data.get("preprocessing"), dict) else {}
    post = data.get("postprocessing") if isinstance(data.get("postprocessing"), dict) else {}
    training = data.get("training_config") if isinstance(data.get("training_config"), dict) else {}
    found: list[str] = []
    for skill in skills:
        if not skill.enabled:
            continue
        if skill.id in ALWAYS_ON_SKILL_IDS:
            if skill.id not in found:
                found.append(skill.id)
            continue
        if entrypoint_matches_pipeline(
            skill.entrypoint,
            preprocessing=pre,
            postprocessing=post,
            training=training,
        ):
            if skill.id not in found:
                found.append(skill.id)
    return found


class SkillsStore:
    def __init__(self, store: BlobStore | None = None) -> None:
        self.store = store or get_blob_store()

    def _read_raw(self) -> dict | None:
        data = self.store.read_json(CATALOG_KEY)
        if isinstance(data, dict):
            return data
        local = _local_catalog_path()
        if local.is_file():
            return json.loads(local.read_text(encoding="utf-8"))
        return None

    def ensure_seeded(self) -> SkillsCatalog:
        raw = self._read_raw()
        if raw and isinstance(raw.get("skills"), list) and raw["skills"]:
            return self.get_catalog(refresh=True)
        catalog = SkillsCatalog(version="1", updated_at=_now(), skills=[SkillItem.model_validate(s) for s in default_seed_skills()])
        self.save_catalog(catalog)
        return catalog

    def get_catalog(self, *, refresh: bool = False) -> SkillsCatalog:
        global _catalog_cache
        raw = self._read_raw()
        if not raw:
            return self.ensure_seeded()
        updated_at = raw.get("updated_at")
        if _catalog_cache is not None and not refresh:
            cached_at, cached = _catalog_cache
            if cached_at == updated_at:
                return cached
        catalog = SkillsCatalog.model_validate(raw)
        _catalog_cache = (updated_at, catalog)
        return catalog

    def save_catalog(self, catalog: SkillsCatalog) -> SkillsCatalog:
        global _catalog_cache
        catalog.updated_at = _now()
        payload = catalog.model_dump()
        self.store.write_json(CATALOG_KEY, payload)
        local = _local_catalog_path()
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError:
            logger.warning("Could not write local skills catalog fallback")
        _catalog_cache = (catalog.updated_at, catalog)
        return catalog

    def list_skills(self, *, enabled_only: bool = False, task_type: str | None = None) -> list[SkillItem]:
        items = self.get_catalog().skills
        if enabled_only:
            items = [s for s in items if s.enabled]
        if task_type:
            items = [s for s in items if s.matches_task(task_type)]
        return items

    def get_skill(self, skill_id: str) -> SkillItem | None:
        for item in self.get_catalog().skills:
            if item.id == skill_id:
                return item
        return None

    def upsert_skill(self, body: SkillUpsertBody, *, skill_id: str | None = None) -> SkillItem:
        catalog = self.get_catalog(refresh=True)
        sid = (skill_id or body.id or "").strip().lower()
        if not sid or not _ID_RE.match(sid):
            raise ValueError("Skill id must match ^[a-z][a-z0-9_.-]{1,63}$")
        if not is_known_entrypoint(body.entrypoint):
            raise ValueError(f"Unknown entrypoint '{body.entrypoint}'. Pick from the registry.")
        existing = next((s for s in catalog.skills if s.id == sid), None)
        item = SkillItem(
            id=sid,
            name=body.name.strip(),
            description=body.description.strip(),
            stage=body.stage,
            task_types=normalize_task_types(body.task_types),
            entrypoint=body.entrypoint,
            params_schema=body.params_schema or {},
            default_params=body.default_params or {},
            # legacy_flags ignored — apply rules live in skill_registry
            legacy_flags={},
            enabled=body.enabled,
            version=(existing.version + 1) if existing else 1,
            updated_at=_now(),
        )
        if existing:
            catalog.skills = [item if s.id == sid else s for s in catalog.skills]
        else:
            catalog.skills.append(item)
        self.save_catalog(catalog)
        return item

    def delete_skill(self, skill_id: str) -> bool:
        catalog = self.get_catalog(refresh=True)
        before = len(catalog.skills)
        catalog.skills = [s for s in catalog.skills if s.id != skill_id]
        if len(catalog.skills) == before:
            return False
        self.save_catalog(catalog)
        return True

    def format_prompt_section(self, task_type: str | None = None) -> str:
        skills = self.list_skills(enabled_only=True, task_type=task_type)
        if not skills:
            skills = self.list_skills(enabled_only=True)
        lines = [
            "",
            "AVAILABLE PIPELINE SKILLS (choose which to enable):",
            "Return also \"enabled_skills\": [\"skill.id\", ...] — only ids from this list that fit the task.",
            "Runtime applies each enabled skill's default_params via the code registry; you do not need legacy_flags.",
            "You may still set preprocessing/postprocessing/training_config explicitly; skills fill gaps and defaults.",
            "",
        ]
        by_stage: dict[str, list[SkillItem]] = {}
        for s in skills:
            by_stage.setdefault(s.stage, []).append(s)
        for stage in ("preprocessing", "augmentation", "postprocessing"):
            group = by_stage.get(stage) or []
            if not group:
                continue
            lines.append(f"## {stage}")
            for s in group:
                tasks = ",".join(s.task_types)
                lines.append(f"- {s.id} [{s.entrypoint}] (tasks: {tasks})")
                lines.append(f"  {s.name}: {s.description}")
                if s.default_params:
                    lines.append(f"  default_params: {json.dumps(s.default_params)}")
            lines.append("")
        return "\n".join(lines)


_skills_store: SkillsStore | None = None


def get_skills_store() -> SkillsStore:
    global _skills_store
    if _skills_store is None:
        _skills_store = SkillsStore()
    return _skills_store
