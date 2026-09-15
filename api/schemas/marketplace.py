"""Marketplace catalog types — datasets and inference-ready models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.project_spec import TaskType

MarketplaceItemKind = Literal["dataset", "model"]

SUPPORTED_TASK_TYPES: tuple[TaskType, ...] = (
    "classification",
    "multi_label",
    "regression",
    "object_localization",
    "object_detection",
)

# Roboflow Universe–style industry browse categories.
MARKETPLACE_INDUSTRIES: tuple[str, ...] = (
    "Manufacturing",
    "Agriculture",
    "Construction",
    "Logistics",
    "Sports",
    "Self Driving",
    "Gaming",
    "Documents",
)


class MarketplaceDatasetItem(BaseModel):
    id: str
    name: str
    task_type: TaskType
    description: str = ""
    license: str = "Unknown"
    storage_prefix: str
    format: str = ""
    size_bytes: int = 0
    size_label: str = ""
    image_count: int = 0
    class_count: int = 0
    classes: list[str] = Field(default_factory=list)
    target_name: str = ""
    target_unit: str = ""
    year: int | None = None
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    source_url: str | None = None


class MarketplaceModelItem(BaseModel):
    id: str
    name: str
    task_type: TaskType
    description: str = ""
    license: str = "Unknown"
    storage_prefix: str
    architecture: str = ""
    input_resolution: str = "224x224"
    metrics: dict[str, Any] = Field(default_factory=dict)
    classes: list[str] = Field(default_factory=list)
    target_name: str = ""
    target_unit: str = ""
    tags: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    trained_on: str | None = None


class MarketplaceCatalog(BaseModel):
    version: str = "1"
    updated_at: str | None = None
    datasets: list[MarketplaceDatasetItem] = Field(default_factory=list)
    models: list[MarketplaceModelItem] = Field(default_factory=list)


class MarketplaceImportBody(BaseModel):
    item_id: str
