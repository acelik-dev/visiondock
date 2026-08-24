"""Project persistence on Blob / local disk — index + per-project JSON files."""

from __future__ import annotations

import secrets
import uuid
import os
from datetime import datetime, timezone
from typing import Any

from dataset_validation import (
    validate_annotated_dataset,
    validate_classification_dataset,
    validate_multilabel_manifest,
    validate_regression_targets,
)
from schemas.project_spec import ProjectSpec, apply_task_defaults, parse_project_spec
from storage.blob_store import BlobStore, get_blob_store

INDEX_KEY = "projects/index.json"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _is_marketplace_linked_dataset(ds: dict[str, Any]) -> bool:
    return (
        ds.get("source") == "marketplace"
        and ds.get("import_status") == "completed"
        and bool(ds.get("validated"))
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_prefix(project_id: str) -> str:
    return f"projects/{project_id}"


def _sanitize_class_name(class_name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in class_name).strip()
    return safe.replace(" ", "_") or "unknown"


def _classification_prefix(project_id: str) -> str:
    return f"{_project_prefix(project_id)}/datasets/classification"


def _multi_label_prefix(project_id: str) -> str:
    return f"{_project_prefix(project_id)}/datasets/multi_label"


def _regression_prefix(project_id: str) -> str:
    return f"{_project_prefix(project_id)}/datasets/regression"


def _annotated_prefix(project_id: str) -> str:
    return f"{_project_prefix(project_id)}/datasets/annotated"


class ProjectStore:
    def __init__(self, store: BlobStore | None = None) -> None:
        self.store = store or get_blob_store()

    def _read_index(self) -> list[dict[str, Any]]:
        data = self.store.read_json(INDEX_KEY)
        if isinstance(data, list):
            return data
        return []

    def _write_index(self, items: list[dict[str, Any]]) -> None:
        self.store.write_json(INDEX_KEY, items)

    def list_projects(self, *, owner_user_id: int | None = None, owner_email: str | None = None) -> list[dict[str, Any]]:
        rows = sorted(self._read_index(), key=lambda p: p.get("updated_at", ""), reverse=True)
        if owner_user_id is None and not owner_email:
            return rows
        email_key = (owner_email or "").strip().lower()
        filtered: list[dict[str, Any]] = []
        for row in rows:
            pid = row.get("id")
            if not pid:
                continue
            meta = self.get_meta(pid) or {}
            row_owner_id = meta.get("owner_user_id") or row.get("owner_user_id")
            row_owner_email = (meta.get("owner_email") or row.get("owner_email") or "").strip().lower()
            # Prefer email when present so wiped+recreated user ids cannot list foreign projects.
            if email_key and row_owner_email:
                if row_owner_email == email_key:
                    filtered.append(row)
                continue
            if owner_user_id is not None and row_owner_id is not None:
                if int(row_owner_id) == int(owner_user_id):
                    filtered.append(row)
                continue
            if row_owner_id is None and not row_owner_email:
                legacy = (os.getenv("AUTH_USERNAME") or os.getenv("BASIC_AUTH_USERNAME") or "").strip().lower()
                if legacy and email_key == legacy:
                    filtered.append(row)
        return filtered

    def delete_project(self, project_id: str) -> None:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        prefix = f"{_project_prefix(project_id)}/"
        for key in self.store.list_prefix(prefix):
            self.store.delete(key)
        self.store.delete(f"{_project_prefix(project_id)}/meta.json")
        index = [row for row in self._read_index() if row.get("id") != project_id]
        self._write_index(index)

    def get_meta(self, project_id: str) -> dict[str, Any] | None:
        data = self.store.read_json(f"{_project_prefix(project_id)}/meta.json")
        return data if isinstance(data, dict) else None

    def create(
        self,
        name: str | None = None,
        *,
        owner_user_id: int | None = None,
        owner_email: str | None = None,
    ) -> dict[str, Any]:
        project_id = f"prj-{secrets.token_hex(4)}"
        label = name or f"Project {project_id[-4:].upper()}"
        meta = {
            "id": project_id,
            "name": label,
            "status": "discovery",
            "created_at": _now(),
            "updated_at": _now(),
            "sample_count": 0,
            "owner_user_id": owner_user_id,
            "owner_email": (owner_email or "").strip().lower() or None,
            "dataset": {
                "uploaded": False,
                "validated": False,
                "size_bytes": 0,
                "file_name": None,
                "validation": None,
            },
        }
        self.store.write_json(f"{_project_prefix(project_id)}/meta.json", meta)
        index = self._read_index()
        index.append(
            {
                "id": project_id,
                "name": label,
                "status": meta["status"],
                "updated_at": meta["updated_at"],
                "owner_user_id": owner_user_id,
                "owner_email": meta.get("owner_email"),
            }
        )
        self._write_index(index)
        self.store.write_json(f"{_project_prefix(project_id)}/chat/messages.json", [])
        return meta

    def _touch_index(self, project_id: str, meta: dict[str, Any]) -> None:
        index = self._read_index()
        for i, row in enumerate(index):
            if row.get("id") == project_id:
                index[i] = {
                    "id": project_id,
                    "name": meta.get("name", row.get("name")),
                    "status": meta.get("status", row.get("status")),
                    "updated_at": meta.get("updated_at", _now()),
                }
                break
        else:
            index.append(
                {
                    "id": project_id,
                    "name": meta.get("name", project_id),
                    "status": meta.get("status", "discovery"),
                    "updated_at": meta.get("updated_at", _now()),
                }
            )
        self._write_index(index)

    def update_meta(self, project_id: str, patch: dict[str, Any], *, touch_index: bool = True) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        meta.update(patch)
        meta["updated_at"] = _now()
        self.store.write_json(f"{_project_prefix(project_id)}/meta.json", meta)
        if touch_index:
            self._touch_index(project_id, meta)
        return meta

    def write_spec(self, project_id: str, spec: dict[str, Any] | ProjectSpec) -> ProjectSpec:
        if isinstance(spec, dict):
            validated = parse_project_spec(spec)
        else:
            validated = apply_task_defaults(spec)
        self.store.write_json(
            f"{_project_prefix(project_id)}/config/project-spec.json",
            validated.model_dump(),
        )
        return validated

    def save_spec(self, project_id: str, spec: dict[str, Any] | ProjectSpec) -> ProjectSpec:
        validated = self.write_spec(project_id, spec)
        patch: dict[str, Any] = {"status": "configured"}
        if validated.project_name and validated.project_name.strip():
            patch["name"] = validated.project_name.strip()
        self.update_meta(project_id, patch)
        return validated

    def load_spec(self, project_id: str) -> dict[str, Any] | None:
        data = self.store.read_json(f"{_project_prefix(project_id)}/config/project-spec.json")
        return data if isinstance(data, dict) else None

    def save_chat(self, project_id: str, messages: list[dict[str, Any]]) -> None:
        self.store.write_json(f"{_project_prefix(project_id)}/chat/messages.json", messages)

    def load_chat(self, project_id: str) -> list[dict[str, Any]]:
        data = self.store.read_json(f"{_project_prefix(project_id)}/chat/messages.json")
        return data if isinstance(data, list) else []

    def add_sample(self, project_id: str, filename: str, data: bytes, content_type: str) -> dict[str, str]:
        safe = "".join(c for c in filename if c.isalnum() or c in "._-") or "sample.jpg"
        blob_name = f"{uuid.uuid4().hex[:12]}_{safe}"
        key = f"{_project_prefix(project_id)}/samples/{blob_name}"
        self.store.write_bytes(key, data, content_type)
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        count = len(self.list_samples(project_id))
        self.update_meta(project_id, {"sample_count": count})
        return {"id": blob_name, "path": key, "url": f"/api/projects/{project_id}/samples/{blob_name}"}

    def list_samples(self, project_id: str) -> list[str]:
        prefix = f"{_project_prefix(project_id)}/samples/"
        return [k.split("/")[-1] for k in self.store.list_prefix(prefix)]

    def read_sample(self, project_id: str, sample_id: str) -> tuple[bytes, str] | None:
        key = f"{_project_prefix(project_id)}/samples/{sample_id}"
        raw = self.store.read_bytes(key)
        if raw is None:
            return None
        ext = sample_id.lower().split(".")[-1]
        ctype = "image/jpeg"
        if ext == "png":
            ctype = "image/png"
        elif ext == "webp":
            ctype = "image/webp"
        return raw, ctype

    def save_dataset(self, project_id: str, filename: str, data: bytes) -> dict[str, Any]:
        key = f"{_project_prefix(project_id)}/datasets/raw/{filename}"
        self.store.write_bytes(key, data, "application/zip")
        blob_url = self.store.blob_url(key)
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        dataset = meta.get("dataset") or {}
        dataset.update(
            {
                "uploaded": True,
                "validated": False,
                "size_bytes": len(data),
                "file_name": filename,
                "storage_key": key,
                "blob_url": blob_url,
                "url": blob_url or f"/api/projects/{project_id}/dataset/file",
                "validation": None,
            }
        )
        self.update_meta(project_id, {"dataset": dataset, "status": "dataset_uploaded"})
        return dataset

    def read_dataset(self, project_id: str) -> bytes | None:
        meta = self.get_meta(project_id)
        if not meta or not meta.get("dataset", {}).get("file_name"):
            return None
        fname = meta["dataset"]["file_name"]
        return self.store.read_bytes(f"{_project_prefix(project_id)}/datasets/raw/{fname}")

    def mark_dataset_validated(self, project_id: str, validation: dict[str, Any]) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        dataset = meta.get("dataset") or {}
        dataset["validated"] = validation.get("valid", False)
        dataset["validation"] = validation
        status = "dataset_validated" if validation.get("valid") else "dataset_uploaded"
        return self.update_meta(project_id, {"dataset": dataset, "status": status})

    def _list_classification_class_dirs(self, project_id: str) -> list[str]:
        prefix = f"{_classification_prefix(project_id)}/"
        keys = self.store.list_prefix(prefix)
        classes: set[str] = set()
        for key in keys:
            rel = key[len(prefix) :] if key.startswith(prefix) else key
            parts = rel.split("/")
            if parts and parts[0]:
                classes.add(parts[0])
        return sorted(classes)

    def count_classification_images(self, project_id: str, class_name: str | None = None) -> dict[str, int]:
        prefix = f"{_classification_prefix(project_id)}/"
        keys = self.store.list_prefix(prefix)
        counts: dict[str, int] = {}
        for key in keys:
            rel = key[len(prefix) :] if key.startswith(prefix) else key
            parts = rel.split("/")
            if len(parts) < 2:
                continue
            cls_dir, fname = parts[0], parts[-1]
            ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
            if ext not in IMAGE_EXT:
                continue
            if class_name and cls_dir != _sanitize_class_name(class_name):
                continue
            counts[cls_dir] = counts.get(cls_dir, 0) + 1
        return counts

    def add_classification_images(
        self,
        project_id: str,
        class_name: str,
        files: list[tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        safe_class = _sanitize_class_name(class_name)
        added = 0
        size_delta = 0
        for filename, data, content_type in files:
            ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ".jpg"
            if ext not in IMAGE_EXT:
                continue
            safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or f"img{added}.jpg"
            blob_name = f"{uuid.uuid4().hex[:12]}_{safe_name}"
            key = f"{_classification_prefix(project_id)}/{safe_class}/{blob_name}"
            self.store.write_bytes(key, data, content_type or "image/jpeg")
            added += 1
            size_delta += len(data)

        counts = self.count_classification_images(project_id)
        spec = self.load_spec(project_id)
        expected = spec.get("classes") if spec else None
        class_counts: dict[str, int] = {}
        if expected:
            for cls in expected:
                class_counts[cls] = counts.get(_sanitize_class_name(cls), 0)
        else:
            for cls_dir, count in counts.items():
                class_counts[cls_dir] = count

        validation = validate_classification_dataset(expected, class_counts)
        storage_prefix = f"{_classification_prefix(project_id)}/"
        dataset = meta.get("dataset") or {}
        dataset.update(
            {
                "mode": "classification",
                "uploaded": sum(class_counts.values()) > 0,
                "validated": validation.get("valid", False),
                "size_bytes": int(dataset.get("size_bytes") or 0) + size_delta,
                "file_name": None,
                "storage_key": storage_prefix,
                "blob_url": self.store.blob_url(storage_prefix.rstrip("/") + "/manifest.json"),
                "url": f"/api/projects/{project_id}/dataset/classification",
                "classes": {
                    cls: {"count": class_counts.get(cls, 0), "storage_dir": _sanitize_class_name(cls)}
                    for cls in (expected or list(class_counts.keys()))
                },
                "validation": validation,
            }
        )
        status = "dataset_validated" if validation.get("valid") else "dataset_uploaded"
        self.update_meta(project_id, {"dataset": dataset, "status": status})
        return {"added": added, "class_name": class_name, "class_counts": class_counts, "validation": validation}

    def get_classification_status(self, project_id: str) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        ds = meta.get("dataset") or {}
        if _is_marketplace_linked_dataset(ds) and ds.get("mode") == "classification":
            class_counts: dict[str, int] = {}
            for cls, info in (ds.get("classes") or {}).items():
                if isinstance(info, dict):
                    class_counts[cls] = int(info.get("count") or 0)
                else:
                    class_counts[cls] = int(info or 0)
            validation = ds.get("validation") or {}
            total = sum(class_counts.values()) or int(ds.get("image_count") or 0)
            return {
                "mode": "classification",
                "classes": class_counts,
                "total_images": total,
                "validated": True,
                "validation": validation,
                "dataset": ds,
            }
        spec = self.load_spec(project_id)
        expected = spec.get("classes") if spec else None
        raw_counts = self.count_classification_images(project_id)
        class_counts: dict[str, int] = {}
        if expected:
            for cls in expected:
                class_counts[cls] = raw_counts.get(_sanitize_class_name(cls), 0)
        else:
            class_counts = dict(raw_counts)
        validation = validate_classification_dataset(expected, class_counts)
        return {
            "mode": "classification",
            "classes": class_counts,
            "total_images": sum(class_counts.values()),
            "validated": validation.get("valid", False),
            "validation": validation,
            "dataset": meta.get("dataset"),
        }

    def clear_classification_class(self, project_id: str, class_name: str) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        safe_class = _sanitize_class_name(class_name)
        prefix = f"{_classification_prefix(project_id)}/{safe_class}/"
        for key in self.store.list_prefix(prefix):
            self.store.delete(key)
        return self.get_classification_status(project_id)

    def revalidate_classification(self, project_id: str) -> dict[str, Any]:
        status = self.get_classification_status(project_id)
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        validation = status["validation"]
        dataset = meta.get("dataset") or {}
        dataset.update(
            {
                "mode": "classification",
                "uploaded": status["total_images"] > 0,
                "validated": validation.get("valid", False),
                "validation": validation,
                "classes": {
                    cls: {"count": status["classes"].get(cls, 0), "storage_dir": _sanitize_class_name(cls)}
                    for cls in status["classes"]
                },
                "storage_key": f"{_classification_prefix(project_id)}/",
            }
        )
        ds_status = "dataset_validated" if validation.get("valid") else "dataset_uploaded"
        self.update_meta(project_id, {"dataset": dataset, "status": ds_status})
        return status

    def _list_image_basenames(self, prefix: str) -> set[str]:
        basenames: set[str] = set()
        for key in self.store.list_prefix(prefix):
            fname = key.split("/")[-1]
            ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
            if ext in IMAGE_EXT:
                basenames.add(fname)
        return basenames

    def add_multi_label_images(
        self,
        project_id: str,
        files: list[tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        prefix = f"{_multi_label_prefix(project_id)}/images/"
        added = 0
        size_delta = 0
        for filename, data, content_type in files:
            ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ".jpg"
            if ext not in IMAGE_EXT:
                continue
            safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or f"img{added}.jpg"
            key = f"{prefix}{uuid.uuid4().hex[:12]}_{safe_name}"
            self.store.write_bytes(key, data, content_type or "image/jpeg")
            added += 1
            size_delta += len(data)
        return self._revalidate_multi_label(project_id, added=added, size_delta=size_delta)

    def save_multi_label_manifest(
        self,
        project_id: str,
        filename: str,
        data: bytes,
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        key = f"{_multi_label_prefix(project_id)}/manifest/{filename}"
        self.store.write_bytes(key, data, "application/octet-stream")
        return self._revalidate_multi_label(project_id, manifest_name=filename)

    def _revalidate_multi_label(
        self,
        project_id: str,
        added: int = 0,
        size_delta: int = 0,
        manifest_name: str | None = None,
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        spec = self.load_spec(project_id)
        expected = spec.get("classes") if spec else None
        images = self._list_image_basenames(f"{_multi_label_prefix(project_id)}/images/")
        manifest_key = None
        manifest_data = None
        for key in self.store.list_prefix(f"{_multi_label_prefix(project_id)}/manifest/"):
            manifest_key = key
            manifest_data = self.store.read_bytes(key)
            manifest_name = key.split("/")[-1]
            break

        validation: dict[str, Any] = {"valid": False, "errors": ["Upload images and a label manifest."], "warnings": [], "stats": {}}
        if manifest_data and images:
            validation = validate_multilabel_manifest(manifest_data, manifest_name or "manifest.csv", images, expected)

        dataset = meta.get("dataset") or {}
        dataset.update(
            {
                "mode": "multi_label",
                "uploaded": len(images) > 0,
                "validated": validation.get("valid", False),
                "size_bytes": int(dataset.get("size_bytes") or 0) + size_delta,
                "file_name": manifest_name,
                "storage_key": f"{_multi_label_prefix(project_id)}/",
                "url": f"/api/projects/{project_id}/dataset/status",
                "validation": validation,
            }
        )
        status = "dataset_validated" if validation.get("valid") else "dataset_uploaded"
        self.update_meta(project_id, {"dataset": dataset, "status": status})
        return {"added": added, "image_count": len(images), "validation": validation}

    def add_regression_images(
        self,
        project_id: str,
        files: list[tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        prefix = f"{_regression_prefix(project_id)}/images/"
        added = 0
        size_delta = 0
        for filename, data, content_type in files:
            ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ".jpg"
            if ext not in IMAGE_EXT:
                continue
            safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or f"img{added}.jpg"
            key = f"{prefix}{uuid.uuid4().hex[:12]}_{safe_name}"
            self.store.write_bytes(key, data, content_type or "image/jpeg")
            added += 1
            size_delta += len(data)
        return self._revalidate_regression(project_id, added=added, size_delta=size_delta)

    def save_regression_targets(
        self,
        project_id: str,
        filename: str,
        data: bytes,
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        key = f"{_regression_prefix(project_id)}/targets/{filename}"
        self.store.write_bytes(key, data, "text/csv")
        return self._revalidate_regression(project_id, targets_name=filename)

    def _revalidate_regression(
        self,
        project_id: str,
        added: int = 0,
        size_delta: int = 0,
        targets_name: str | None = None,
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        spec = self.load_spec(project_id)
        target_name = (spec or {}).get("target_name") or "target"
        images = self._list_image_basenames(f"{_regression_prefix(project_id)}/images/")
        targets_data = None
        for key in self.store.list_prefix(f"{_regression_prefix(project_id)}/targets/"):
            targets_data = self.store.read_bytes(key)
            targets_name = key.split("/")[-1]
            break

        validation: dict[str, Any] = {"valid": False, "errors": ["Upload images and a target CSV."], "warnings": [], "stats": {}}
        if targets_data and images:
            validation = validate_regression_targets(targets_data, images, target_name)

        dataset = meta.get("dataset") or {}
        dataset.update(
            {
                "mode": "regression",
                "uploaded": len(images) > 0,
                "validated": validation.get("valid", False),
                "size_bytes": int(dataset.get("size_bytes") or 0) + size_delta,
                "file_name": targets_name,
                "storage_key": f"{_regression_prefix(project_id)}/",
                "url": f"/api/projects/{project_id}/dataset/status",
                "validation": validation,
            }
        )
        status = "dataset_validated" if validation.get("valid") else "dataset_uploaded"
        self.update_meta(project_id, {"dataset": dataset, "status": status})
        return {"added": added, "image_count": len(images), "validation": validation}

    def save_annotated_dataset(
        self,
        project_id: str,
        filename: str,
        data: bytes,
        task_type: str = "object_detection",
    ) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        key = f"{_annotated_prefix(project_id)}/raw/{filename}"
        self.store.write_bytes(key, data, "application/zip")
        spec = self.load_spec(project_id)
        expected = spec.get("classes") if spec else None
        validation = validate_annotated_dataset(data, task_type, expected)
        dataset = meta.get("dataset") or {}
        dataset.update(
            {
                "mode": task_type,
                "uploaded": True,
                "validated": validation.get("valid", False),
                "size_bytes": len(data),
                "file_name": filename,
                "storage_key": key,
                "blob_url": self.store.blob_url(key),
                "url": f"/api/projects/{project_id}/dataset/file",
                "validation": validation,
            }
        )
        status = "dataset_validated" if validation.get("valid") else "dataset_uploaded"
        self.update_meta(project_id, {"dataset": dataset, "status": status})
        return {"validation": validation, "dataset": dataset}

    def get_dataset_status(self, project_id: str) -> dict[str, Any]:
        meta = self.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)
        spec = self.load_spec(project_id)
        task_type = (spec or {}).get("task_type") or "classification"
        ds = meta.get("dataset") or {}
        mode = ds.get("mode") or task_type

        if mode == "classification" or task_type == "classification":
            status = self.get_classification_status(project_id)
            return {
                "mode": "classification",
                "task_type": task_type,
                **status,
                "summary": status.get("validation", {}).get("stats", {}),
            }

        if mode == "multi_label" or task_type == "multi_label":
            if _is_marketplace_linked_dataset(ds):
                validation = ds.get("validation") or {}
                total = int(validation.get("stats", {}).get("image_count") or ds.get("image_count") or 0)
                return {
                    "mode": "multi_label",
                    "task_type": task_type,
                    "total_images": total,
                    "validated": True,
                    "validation": validation,
                    "summary": validation.get("stats", {}),
                    "dataset": ds,
                }
            images = self._list_image_basenames(f"{_multi_label_prefix(project_id)}/images/")
            validation = ds.get("validation") or {}
            if not validation.get("stats"):
                manifest_data = None
                manifest_name = "manifest.csv"
                for key in self.store.list_prefix(f"{_multi_label_prefix(project_id)}/manifest/"):
                    manifest_data = self.store.read_bytes(key)
                    manifest_name = key.split("/")[-1]
                    break
                if manifest_data:
                    expected = spec.get("classes") if spec else None
                    validation = validate_multilabel_manifest(manifest_data, manifest_name, images, expected)
            return {
                "mode": "multi_label",
                "task_type": task_type,
                "total_images": len(images),
                "validated": validation.get("valid", False),
                "validation": validation,
                "summary": validation.get("stats", {}),
                "dataset": ds,
            }

        if mode == "regression" or task_type == "regression":
            if _is_marketplace_linked_dataset(ds):
                validation = ds.get("validation") or {}
                total = int(validation.get("stats", {}).get("image_count") or ds.get("image_count") or 0)
                return {
                    "mode": "regression",
                    "task_type": task_type,
                    "total_images": total,
                    "validated": True,
                    "validation": validation,
                    "summary": validation.get("stats", {}),
                    "dataset": ds,
                }
            images = self._list_image_basenames(f"{_regression_prefix(project_id)}/images/")
            validation = ds.get("validation") or {}
            if not validation.get("stats"):
                targets_data = None
                target_name = (spec or {}).get("target_name") or "target"
                for key in self.store.list_prefix(f"{_regression_prefix(project_id)}/targets/"):
                    targets_data = self.store.read_bytes(key)
                    break
                if targets_data:
                    validation = validate_regression_targets(targets_data, images, target_name)
            return {
                "mode": "regression",
                "task_type": task_type,
                "total_images": len(images),
                "validated": validation.get("valid", False),
                "validation": validation,
                "summary": validation.get("stats", {}),
                "dataset": ds,
            }

        if mode in ("object_detection", "object_localization") or task_type in (
            "object_detection",
            "object_localization",
        ):
            if _is_marketplace_linked_dataset(ds):
                validation = ds.get("validation") or {}
                total = int(validation.get("stats", {}).get("image_count") or ds.get("image_count") or 0)
                return {
                    "mode": task_type,
                    "task_type": task_type,
                    "total_images": total,
                    "validated": True,
                    "validation": validation,
                    "summary": validation.get("stats", {}),
                    "dataset": ds,
                }
            validation = ds.get("validation") or {}
            raw = self.read_annotated_dataset(project_id)
            if raw and not validation.get("stats"):
                expected = spec.get("classes") if spec else None
                validation = validate_annotated_dataset(raw, task_type, expected)
            return {
                "mode": task_type,
                "task_type": task_type,
                "total_images": validation.get("stats", {}).get("image_count", 0),
                "validated": validation.get("valid", False),
                "validation": validation,
                "summary": validation.get("stats", {}),
                "dataset": ds,
            }

        return {
            "mode": mode,
            "task_type": task_type,
            "validated": ds.get("validated", False),
            "validation": ds.get("validation"),
            "summary": (ds.get("validation") or {}).get("stats", {}),
            "dataset": ds,
        }

    def read_annotated_dataset(self, project_id: str) -> bytes | None:
        meta = self.get_meta(project_id)
        if not meta:
            return None
        ds = meta.get("dataset") or {}
        fname = ds.get("file_name")
        if not fname:
            return None
        return self.store.read_bytes(f"{_annotated_prefix(project_id)}/raw/{fname}")
