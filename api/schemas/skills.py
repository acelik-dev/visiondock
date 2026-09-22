"""VisionDock skills catalog — VLM context + code entrypoint mapping."""

from __future__ import annotations
import logging

from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.project_spec import VALID_TASK_TYPES

SkillStage = Literal["preprocessing", "postprocessing", "augmentation"]

VALID_STAGES: frozenset[str] = frozenset({"preprocessing", "postprocessing", "augmentation"})

_TASK_TYPE_SYNONYMS: dict[str, str] = {
    "detection": "object_detection",
    "object_detection": "object_detection",
    "od": "object_detection",
    "localization": "object_localization",
    "localisation": "object_localization",
    "object_localization": "object_localization",
    "multilabel": "multi_label",
    "multi_label": "multi_label",
    "multilabel_classification": "multi_label",
    "classification": "classification",
    "regression": "regression",
}

class SkillItem(BaseModel):
    id: str
    name: str
    description: str = ""
    stage: SkillStage
    task_types: list[str] = Field(default_factory=lambda: ["*"])
    entrypoint: str
    params_schema: dict[str, Any] = Field(default_factory=dict)
    default_params: dict[str, Any] = Field(default_factory=dict)
    legacy_flags: dict[str, Any] = Field(
        default_factory=dict,
        description="Deprecated — ignored. Apply rules live in skill_registry.",
    )
    enabled: bool = True
    version: int = 1
    updated_at: str | None = None

    def matches_task(self, task_type: str | None) -> bool:
        if not self.task_types or "*" in self.task_types:
            return True
        if not task_type:
            return True
        return task_type in self.task_types


class SkillsCatalog(BaseModel):
    version: str = "1"
    updated_at: str | None = None
    skills: list[SkillItem] = Field(default_factory=list)


class SkillUpsertBody(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    stage: SkillStage
    task_types: list[str] = Field(default_factory=lambda: ["*"])
    entrypoint: str
    params_schema: dict[str, Any] = Field(default_factory=dict)
    default_params: dict[str, Any] = Field(default_factory=dict)
    legacy_flags: dict[str, Any] = Field(
        default_factory=dict,
        description="Deprecated — ignored. Apply rules live in skill_registry.",
    )
    enabled: bool = True


def normalize_task_types(values: list[str] | None) -> list[str]:
    if not values:
        return ["*"]
    out: list[str] = []
    for raw in values:
        text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not text:
            continue
        if text in ("*", "all", "any"):
            return ["*"]
        text = _TASK_TYPE_SYNONYMS.get(text, text)
        if text in VALID_TASK_TYPES and text not in out:
            out.append(text)
        else:
            # [YENİ EKLENDİ]: Eşleşmeyen bir değer varsa sessizce yutmak yerine log düşüyoruz
            logger.warning(
                "normalize_task_types: discarding unrecognized task type %r (raw input %r)",
                text,
                raw,
            )
    return out or ["*"]
