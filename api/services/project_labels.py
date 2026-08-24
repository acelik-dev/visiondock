"""Human-readable project titles for lists and navigation."""

from __future__ import annotations

from typing import Any

_GENERIC_NAMES = frozenset({"vision workspace", "project workspace", ""})


def _clean_dataset_label(file_name: str | None) -> str | None:
    if not file_name:
        return None
    base = file_name.rsplit(".", 1)[0]
    return base.replace("_", " ").replace("-", " ").strip()[:80] or None


def _task_label(task: str | None) -> str | None:
    if not task:
        return None
    return task.replace("_", " ").title()


def resolve_project_display(
    meta: dict[str, Any], spec: dict[str, Any] | None
) -> dict[str, str | None]:
    """Return display_name and subtitle for UI lists."""
    spec = spec or {}
    task = spec.get("task_type") or meta.get("detected_task")
    dataset = meta.get("dataset") or {}
    file_name = dataset.get("file_name")
    stats = (dataset.get("validation") or {}).get("stats") or {}
    image_count = stats.get("image_count")

    spec_name = (spec.get("project_name") or "").strip()
    meta_name = (meta.get("name") or "").strip()
    dataset_label = _clean_dataset_label(file_name)
    task_text = _task_label(str(task) if task else None)
    short_id = (meta.get("id") or "")[-8:].upper()

    if spec_name:
        display_name = spec_name
    elif meta_name and meta_name.lower() not in _GENERIC_NAMES:
        display_name = meta_name
    elif dataset_label:
        display_name = dataset_label
    elif task_text:
        display_name = f"{task_text} ({short_id})"
    else:
        display_name = f"Project {short_id}"

    subtitle_parts: list[str] = []
    if task_text:
        subtitle_parts.append(task_text)
    if dataset_label and dataset_label.lower() != display_name.lower():
        subtitle_parts.append(dataset_label)
    if image_count:
        subtitle_parts.append(f"{int(image_count):,} images")
    if meta.get("training", {}).get("status") == "Completed":
        metrics = meta.get("training", {}).get("metrics") or {}
        if metrics.get("mAP50") is not None:
            subtitle_parts.append(f"mAP50 {float(metrics['mAP50']):.2f}")

    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None
    return {
        "display_name": display_name,
        "subtitle": subtitle,
        "task_type": str(task) if task else None,
    }


def should_sync_meta_name(meta: dict[str, Any], spec: dict[str, Any] | None) -> str | None:
    """If meta name is generic, return a better name from spec/dataset."""
    current = (meta.get("name") or "").strip()
    if current and current.lower() not in _GENERIC_NAMES:
        return None
    resolved = resolve_project_display(meta, spec)
    new_name = resolved.get("display_name")
    if not new_name or new_name == current:
        return None
    return str(new_name)
