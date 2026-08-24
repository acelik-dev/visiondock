"""Import marketplace datasets and models into projects."""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

from dataset_validation import MIN_CLASSES_WITH_DATA, validate_classification_dataset
from schemas.marketplace import MarketplaceDatasetItem, MarketplaceModelItem
from services.inference_service import get_inference_service
from services.marketplace_import_queue import is_inflight, reserve_import, start_import
from services.marketplace_store import MarketplaceStore, get_marketplace_store
from services.project_store import ProjectStore, _sanitize_class_name


def _sanitize_job_id(item_id: str) -> str:
    safe = re.sub(r"[^a-z0-9-]", "-", item_id.lower()).strip("-")
    return f"mp-{safe}"[:48]


def _project_task_type(meta: dict[str, Any], spec: dict[str, Any] | None) -> str | None:
    if spec and spec.get("task_type"):
        return str(spec["task_type"])
    if meta.get("detected_task"):
        return str(meta["detected_task"])
    return None


def _assert_task_match(project_task: str | None, item_task: str, item_name: str) -> None:
    if project_task and project_task != item_task:
        raise ValueError(
            f"Task type mismatch: active project is '{project_task}' but "
            f"'{item_name}' requires '{item_task}'. Update the project spec or pick another item."
        )


def _clear_project_prefix(store: ProjectStore, prefix: str) -> None:
    for key in store.store.list_prefix(prefix):
        store.store.delete(key)


_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

_MODEL_DISPLAY_NAMES: dict[str, str] = {
    "efficientnet-imagenette": "EfficientNet · Image classification",
    "efficientnet-cifar10": "EfficientNet · Small-image classification",
    "efficientnet-voc-multilabel": "EfficientNet · Multi-label tags",
    "efficientnet-age-regression": "EfficientNet · Numeric regression",
    "yolov8n-voc-detection": "YOLOv8n · Multi-object detection",
    "yolov8n-voc-localization": "YOLOv8n · Single-object localization",
}


def _model_display_name(item: MarketplaceModelItem) -> str:
    if item.id in _MODEL_DISPLAY_NAMES:
        return _MODEL_DISPLAY_NAMES[item.id]
    if item.architecture:
        return item.architecture.replace("_", "-")
    return item.name.split("·")[0].strip() or item.name


class MarketplaceImportService:
    def __init__(
        self,
        marketplace: MarketplaceStore | None = None,
        projects: ProjectStore | None = None,
    ) -> None:
        self.marketplace = marketplace or get_marketplace_store()
        self.projects = projects or ProjectStore()

    def begin_dataset_import(self, project_id: str, item_id: str) -> dict[str, Any]:
        """Return immediately; copy dataset files and update meta in a background thread."""
        item = self.marketplace.get_dataset(item_id)
        if item is None:
            raise KeyError(f"Marketplace dataset '{item_id}' not found")

        meta = self.projects.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)

        if is_inflight(project_id):
            return self._pending_import_response(item, meta)

        reserve_import(project_id)
        pending_meta = dict(meta)
        pending_meta["name"] = item.name
        pending_meta["dataset"] = {
            **(meta.get("dataset") or {}),
            "marketplace_item_id": item.id,
            "marketplace_name": item.name,
            "source": "marketplace",
            "import_status": "in_progress",
            "uploaded": False,
            "validated": False,
        }
        return self._pending_import_response(item, pending_meta)

    def run_full_dataset_import(self, project_id: str, item_id: str) -> None:
        if not is_inflight(project_id):
            reserve_import(project_id)

        def _run() -> dict[str, Any]:
            try:
                return self._full_dataset_import(project_id, item_id)
            except Exception:
                meta = self.projects.get_meta(project_id) or {}
                ds = dict(meta.get("dataset") or {})
                ds["import_status"] = "failed"
                self.projects.update_meta(project_id, {"dataset": ds}, touch_index=False)
                raise

        start_import(project_id, _run)

    def _full_dataset_import(self, project_id: str, item_id: str) -> dict[str, Any]:
        item = self.marketplace.get_dataset(item_id)
        if item is None:
            raise KeyError(f"Marketplace dataset '{item_id}' not found")

        meta = self.projects.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)

        spec = self.projects.load_spec(project_id)
        project_task = _project_task_type(meta, spec)
        _assert_task_match(project_task, item.task_type, item.name)

        if not self.marketplace.item_exists_in_storage(item.storage_prefix):
            raise FileNotFoundError(
                f"Dataset files not found in storage for '{item_id}'. Run scripts/seed-marketplace.py first."
            )

        self._sync_spec_from_dataset(project_id, spec, item)
        dataset = dict(meta.get("dataset") or {})
        dataset.update(
            {
                "marketplace_item_id": item.id,
                "marketplace_name": item.name,
                "source": "marketplace",
                "import_status": "in_progress",
                "uploaded": False,
                "validated": False,
            }
        )
        self.projects.update_meta(
            project_id,
            {
                "name": item.name,
                "dataset": dataset,
                "status": "dataset_uploading",
            },
            touch_index=False,
        )
        return self._finish_dataset_import(project_id, item)

    def _finish_dataset_import(self, project_id: str, item: MarketplaceDatasetItem) -> dict[str, Any]:
        result = self._copy_dataset(project_id, item)
        updated_meta = self.projects.get_meta(project_id) or {}
        ds = dict(updated_meta.get("dataset") or {})
        ds["marketplace_item_id"] = item.id
        ds["marketplace_name"] = item.name
        ds["source"] = "marketplace"
        ds["import_status"] = "completed"
        self.projects.update_meta(
            project_id,
            {
                "dataset": ds,
                "status": updated_meta.get("status", "dataset_uploaded"),
            },
            touch_index=True,
        )
        return result

    def import_dataset(self, project_id: str, item_id: str) -> dict[str, Any]:
        return self.link_dataset_from_marketplace(project_id, item_id)

    def link_dataset_from_marketplace(self, project_id: str, item_id: str) -> dict[str, Any]:
        """Link a marketplace dataset by reference — no blob copy."""
        item = self.marketplace.get_dataset(item_id)
        if item is None:
            raise KeyError(f"Marketplace dataset '{item_id}' not found")

        meta = self.projects.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)

        spec = self.projects.load_spec(project_id)
        project_task = _project_task_type(meta, spec)
        _assert_task_match(project_task, item.task_type, item.name)

        if not self.marketplace.item_exists_in_storage(item.storage_prefix):
            raise FileNotFoundError(
                f"Dataset files not found in storage for '{item_id}'. Run scripts/seed-marketplace.py first."
            )

        self._sync_spec_from_dataset(project_id, spec, item)
        link = self._build_marketplace_link(item)
        validation = link["validation"]
        spec_out = self._dataset_spec_payload(item)

        dataset = dict(meta.get("dataset") or {})
        dataset.update(
            {
                "mode": link["mode"],
                "marketplace_item_id": item.id,
                "marketplace_name": item.name,
                "source": "marketplace",
                "import_status": "completed",
                "uploaded": True,
                "validated": validation.get("valid", True),
                "size_bytes": item.size_bytes or int(dataset.get("size_bytes") or 0),
                "storage_key": link["storage_key"],
                "file_name": link.get("file_name"),
                "validation": validation,
            }
        )
        if link.get("classes"):
            dataset["classes"] = link["classes"]
        if link.get("blob_url"):
            dataset["blob_url"] = link["blob_url"]

        self.projects.update_meta(
            project_id,
            {
                "name": item.name,
                "dataset": dataset,
                "status": "dataset_validated" if validation.get("valid", True) else "dataset_uploaded",
            },
            touch_index=True,
        )

        updated_meta = self.projects.get_meta(project_id) or meta
        return {
            "success": True,
            "item_id": item.id,
            "item_name": item.name,
            "task_type": item.task_type,
            "import_status": "completed",
            "files_copied": 0,
            "validation": validation,
            "mode": link["mode"],
            "project": updated_meta,
            "spec": spec_out,
        }

    def bootstrap_project_from_model(self, project_id: str, item_id: str) -> dict[str, Any]:
        """Start a training project from a marketplace model template — user supplies their own data."""
        item = self.marketplace.get_model(item_id)
        if item is None:
            raise KeyError(f"Marketplace model '{item_id}' not found")

        meta = self.projects.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)

        display_name = _model_display_name(item)
        spec_saved = self._write_model_spec(project_id, item)
        arch = item.architecture or (
            "efficientnet_b0"
            if item.task_type in ("classification", "multi_label", "regression")
            else "yolov8n"
        )
        # Catalog classes are reference-only (Imagenette/VOC demo labels). The
        # customer defines their own labels when they upload data — never lock them in.
        example_classes = [str(c).strip() for c in (item.classes or []) if str(c).strip()]

        self.projects.update_meta(
            project_id,
            {
                "name": display_name,
                "status": "discovery",
                "model_template": {
                    "source": "marketplace",
                    "marketplace_item_id": item.id,
                    "marketplace_name": display_name,
                    "architecture": arch,
                    "input_resolution": item.input_resolution,
                    "reference_metrics": item.metrics or {},
                    "trained_on": item.trained_on,
                    "example_classes": example_classes,
                },
            },
            touch_index=True,
        )

        updated_meta = self.projects.get_meta(project_id) or meta
        return {
            "success": True,
            "item_id": item.id,
            "item_name": item.name,
            "task_type": item.task_type,
            "architecture": arch,
            "project": updated_meta,
            "spec": spec_saved,
        }

    def _model_spec_payload(self, item: MarketplaceModelItem) -> dict[str, Any]:
        arch = item.architecture or (
            "efficientnet_b0"
            if item.task_type in ("classification", "multi_label", "regression")
            else "yolov8n"
        )
        # Lock architecture + task type only. Classes stay empty so Step 2 asks
        # the customer for their own labels (catalog names are demo reference).
        payload: dict[str, Any] = {
            "project_name": _model_display_name(item),
            "task_type": item.task_type,
            "classes": [],
            "recommended_model": arch,
            "description": item.description
            or f"Train a {arch} model on your own labeled images.",
            "target_name": "",
            "target_unit": "",
        }
        if item.task_type == "regression":
            # Soft defaults the user can rename — not a locked label set.
            payload["target_name"] = item.target_name or "target"
            payload["target_unit"] = item.target_unit or ""
        return payload

    def _write_model_spec(self, project_id: str, item: MarketplaceModelItem) -> dict[str, Any]:
        from schemas.project_spec import ProjectSpec, apply_task_defaults

        validated = apply_task_defaults(ProjectSpec.model_validate(self._model_spec_payload(item)))
        self.projects.write_spec(project_id, validated)
        return validated.model_dump()

    def _dataset_spec_payload(self, item: MarketplaceDatasetItem) -> dict[str, Any]:
        return {
            "project_name": item.name,
            "task_type": item.task_type,
            "classes": item.classes or [],
            "recommended_model": "efficientnet_b0"
            if item.task_type in ("classification", "multi_label", "regression")
            else "yolov8n",
            "description": item.description,
            "target_name": item.target_name or "target",
            "target_unit": item.target_unit or "",
        }

    def _catalog_class_counts(self, item: MarketplaceDatasetItem) -> dict[str, int]:
        classes = item.classes or []
        total = item.image_count or 0
        if not classes:
            return {}
        if total <= 0:
            return dict.fromkeys(classes, 1)
        base, remainder = divmod(total, len(classes))
        return {cls: base + (1 if idx < remainder else 0) for idx, cls in enumerate(classes)}

    def _catalog_validation(self, item: MarketplaceDatasetItem) -> dict[str, Any]:
        if item.task_type == "classification":
            class_counts = self._catalog_class_counts(item)
            validation = validate_classification_dataset(item.classes or None, class_counts)
            if (item.image_count or 0) > 0 and len(item.classes or []) >= MIN_CLASSES_WITH_DATA:
                validation = {**validation, "valid": True, "errors": []}
            stats = dict(validation.get("stats") or {})
            stats["source"] = "marketplace_catalog"
            validation["stats"] = stats
            return validation

        stats: dict[str, Any] = {
            "image_count": item.image_count or 0,
            "class_count": item.class_count or len(item.classes or []),
            "source": "marketplace_catalog",
        }
        valid = (item.image_count or 0) > 0
        return {
            "valid": valid,
            "errors": [] if valid else ["Marketplace catalog reports no images for this dataset."],
            "warnings": [],
            "stats": stats,
        }

    def _prefix_has_classification_layout(self, prefix: str) -> bool:
        for key in self.projects.store.list_prefix(prefix):
            rel = key[len(prefix) :] if key.startswith(prefix) else key
            parts = rel.split("/")
            if len(parts) < 2:
                continue
            fname = parts[-1].lower()
            if any(fname.endswith(ext) for ext in _IMAGE_SUFFIXES):
                return True
        return False

    def _build_marketplace_link(self, item: MarketplaceDatasetItem) -> dict[str, Any]:
        src = item.storage_prefix.rstrip("/") + "/"
        task = item.task_type
        validation = self._catalog_validation(item)
        link: dict[str, Any] = {
            "mode": task,
            "validation": validation,
            "storage_key": src,
            "file_name": None,
        }

        if task == "classification":
            class_prefix = f"{src}classification/"
            if self._prefix_has_classification_layout(class_prefix):
                link["storage_key"] = class_prefix
            elif self.projects.store.exists(f"{src}classification.zip"):
                zip_key = f"{src}classification.zip"
                link["storage_key"] = zip_key
                link["blob_url"] = self.projects.store.blob_url(zip_key)
            else:
                link["storage_key"] = class_prefix
            class_counts = self._catalog_class_counts(item)
            link["classes"] = {
                cls: {"count": class_counts.get(cls, 0), "storage_dir": _sanitize_class_name(cls)}
                for cls in (item.classes or list(class_counts.keys()))
            }
            return link

        if task in ("multi_label", "regression"):
            link["storage_key"] = src
            return link

        if task in ("object_detection", "object_localization"):
            zip_key = None
            for key in self.projects.store.list_prefix(src):
                if key.lower().endswith(".zip"):
                    zip_key = key
                    break
            if not zip_key:
                raise FileNotFoundError(f"No dataset ZIP under {item.storage_prefix}")
            fname = zip_key.split("/")[-1]
            link["storage_key"] = zip_key
            link["file_name"] = fname
            link["blob_url"] = self.projects.store.blob_url(zip_key)
            return link

        raise ValueError(f"Unsupported dataset task type: {task}")

    def _pending_import_response(self, item: MarketplaceDatasetItem, meta: dict[str, Any]) -> dict[str, Any]:
        spec = {
            "project_name": item.name,
            "task_type": item.task_type,
            "classes": item.classes or [],
            "recommended_model": "efficientnet_b0"
            if item.task_type in ("classification", "multi_label", "regression")
            else "yolov8n",
            "description": item.description,
            "target_name": item.target_name or "target",
            "target_unit": item.target_unit or "",
        }
        return {
            "success": True,
            "item_id": item.id,
            "item_name": item.name,
            "task_type": item.task_type,
            "import_status": "in_progress",
            "files_copied": 0,
            "validation": {"valid": False, "errors": []},
            "project": meta,
            "spec": spec,
        }

    def import_model(self, project_id: str, item_id: str) -> dict[str, Any]:
        item = self.marketplace.get_model(item_id)
        if item is None:
            raise KeyError(f"Marketplace model '{item_id}' not found")

        meta = self.projects.get_meta(project_id)
        if meta is None:
            raise KeyError(project_id)

        spec = self.projects.load_spec(project_id)
        project_task = _project_task_type(meta, spec)
        _assert_task_match(project_task, item.task_type, item.name)

        if not self.marketplace.item_exists_in_storage(item.storage_prefix):
            raise FileNotFoundError(
                f"Model artifacts not found in storage for '{item_id}'. Run scripts/seed-marketplace.py first."
            )

        self._sync_spec_from_model(project_id, spec, item)
        job_id = _sanitize_job_id(item.id)
        manifest = self._copy_model_artifacts(project_id, job_id, item)

        self.projects.update_meta(
            project_id,
            {
                "model": manifest,
                "status": "inference_deploying",
                "training": {
                    **(meta.get("training") or {}),
                    "status": "Completed",
                    "job_id": job_id,
                    "source": "marketplace",
                    "marketplace_item_id": item.id,
                },
            },
        )

        inference = get_inference_service()
        inference.ensure_api_key(project_id)
        inference.register_and_deploy(project_id, job_id)

        return {
            "success": True,
            "item_id": item.id,
            "item_name": item.name,
            "task_type": item.task_type,
            "job_id": job_id,
            "deploy_status": inference.deploy_status(project_id),
        }

    def _sync_spec_from_dataset(
        self,
        project_id: str,
        spec: dict[str, Any] | None,
        item: MarketplaceDatasetItem,
    ) -> None:
        patch: dict[str, Any] = {
            "task_type": item.task_type,
            "project_name": (spec or {}).get("project_name") or item.name,
        }
        if item.classes:
            patch["classes"] = item.classes
        if item.task_type == "regression" and item.target_name:
            patch["target_name"] = item.target_name
            patch["target_unit"] = item.target_unit or ""
        if spec:
            merged = {**spec, **patch}
            self.projects.write_spec(project_id, merged)
        else:
            from schemas.project_spec import ProjectSpec, apply_task_defaults

            base = apply_task_defaults(
                ProjectSpec.model_validate(
                    {
                        "project_name": item.name,
                        "task_type": item.task_type,
                        "recommended_model": "efficientnet_b0"
                        if item.task_type in ("classification", "multi_label", "regression")
                        else "yolov8n",
                        "description": item.description,
                        "classes": item.classes,
                        "target_name": item.target_name or "target",
                        "target_unit": item.target_unit or "",
                    }
                )
            )
            self.projects.write_spec(project_id, base)

    def _sync_spec_from_model(
        self,
        project_id: str,
        spec: dict[str, Any] | None,
        item: MarketplaceModelItem,
    ) -> None:
        patch: dict[str, Any] = {
            "task_type": item.task_type,
            "recommended_model": item.architecture or (spec or {}).get("recommended_model", ""),
        }
        if item.classes:
            patch["classes"] = item.classes
        if item.task_type == "regression" and item.target_name:
            patch["target_name"] = item.target_name
            patch["target_unit"] = item.target_unit or ""
        if spec:
            merged = {**spec, **patch}
            self.projects.save_spec(project_id, merged)
        elif item.classes or item.task_type == "regression":
            from schemas.project_spec import ProjectSpec, apply_task_defaults

            base = apply_task_defaults(
                ProjectSpec.model_validate(
                    {
                        "project_name": item.name,
                        "task_type": item.task_type,
                        "recommended_model": item.architecture or "efficientnet_b0",
                        "description": item.description,
                        "classes": item.classes,
                        "target_name": item.target_name or "target",
                        "target_unit": item.target_unit or "",
                    }
                )
            )
            self.projects.save_spec(project_id, base)

    def _copy_dataset(self, project_id: str, item: MarketplaceDatasetItem) -> dict[str, Any]:
        src = item.storage_prefix.rstrip("/") + "/"
        task = item.task_type

        if task == "classification":
            return self._import_classification_dataset(project_id, src)

        if task == "multi_label":
            dest = f"projects/{project_id}/datasets/multi_label/"
            _clear_project_prefix(self.projects, dest)
            count = self.projects.store.copy_prefix(src, dest)
            status = self.projects._revalidate_multi_label(project_id)
            return {"files_copied": count, "validation": status.get("validation"), "mode": "multi_label"}

        if task == "regression":
            dest = f"projects/{project_id}/datasets/regression/"
            _clear_project_prefix(self.projects, dest)
            count = self.projects.store.copy_prefix(src, dest)
            status = self.projects._revalidate_regression(project_id)
            return {"files_copied": count, "validation": status.get("validation"), "mode": "regression"}

        if task in ("object_detection", "object_localization"):
            zip_key = None
            for key in self.projects.store.list_prefix(src):
                if key.lower().endswith(".zip"):
                    zip_key = key
                    break
            if not zip_key:
                raise FileNotFoundError(f"No dataset ZIP under {item.storage_prefix}")
            fname = zip_key.split("/")[-1]
            dest_key = f"projects/{project_id}/datasets/annotated/{fname}"
            _clear_project_prefix(self.projects, f"projects/{project_id}/datasets/annotated/")
            self.projects.store.copy_blob(zip_key, dest_key)
            raw = self.projects.store.read_bytes(dest_key)
            if not raw:
                raise FileNotFoundError(f"Could not read copied dataset ZIP at {dest_key}")
            result = self.projects.save_annotated_dataset(project_id, fname, raw, task_type=task)
            return {
                "files_copied": 1,
                "validation": result.get("validation"),
                "mode": task,
                "file_name": fname,
            }

        raise ValueError(f"Unsupported dataset task type: {task}")

    def _extract_classification_zip(self, zip_key: str, dest: str) -> int:
        raw = self.projects.store.read_bytes(zip_key)
        if not raw:
            return 0
        count = 0
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                if name.endswith("/") or name.startswith("__MACOSX"):
                    continue
                parts = name.split("/")
                if len(parts) == 2 and parts[0] and parts[1]:
                    out_key = f"{dest}{parts[0]}/{parts[1]}"
                elif len(parts) >= 2:
                    out_key = f"{dest}{'/'.join(parts[-2:])}"
                else:
                    continue
                lower = name.lower()
                if not lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                self.projects.store.write_bytes(out_key, zf.read(name))
                count += 1
        return count

    def _import_classification_dataset(self, project_id: str, src: str) -> dict[str, Any]:
        dest = f"projects/{project_id}/datasets/classification/"
        _clear_project_prefix(self.projects, dest)

        copied = self.projects.store.copy_prefix(f"{src}classification/", dest)
        zip_key = f"{src}classification.zip"
        if self.projects.store.exists(zip_key):
            self.projects.store.copy_blob(zip_key, f"{dest}classification.zip")
            copied = max(copied, 1)

        if copied == 0:
            raise FileNotFoundError(f"No classification files found under {src}")

        status = self.projects.revalidate_classification(project_id)
        return {
            "files_copied": copied,
            "validation": status.get("validation"),
            "mode": "classification",
            "import_status": "completed",
        }

    def _copy_model_artifacts(
        self,
        project_id: str,
        job_id: str,
        item: MarketplaceModelItem,
    ) -> dict[str, Any]:
        src = item.storage_prefix.rstrip("/") + "/"
        dest = f"projects/{project_id}/models/{job_id}/"
        _clear_project_prefix(self.projects, dest)
        self.projects.store.copy_prefix(src, dest)

        manifest_key = f"{dest}model.json"
        manifest = self.projects.store.read_json(manifest_key)
        if not isinstance(manifest, dict):
            manifest = {
                "task_type": item.task_type,
                "classes": item.classes,
                "metrics": item.metrics,
                "architecture": item.architecture,
            }

        weights_rel = manifest.get("weights_blob") or "best.pt"
        if not str(weights_rel).startswith("projects/"):
            weights_key = f"{dest}{weights_rel.lstrip('/')}"
            manifest["weights_blob"] = weights_key
        else:
            weights_key = str(weights_rel)

        labels_rel = manifest.get("labels_blob")
        if labels_rel and not str(labels_rel).startswith("projects/"):
            manifest["labels_blob"] = f"{dest}{str(labels_rel).lstrip('/')}"

        onnx_rel = manifest.get("onnx_blob")
        if onnx_rel and not str(onnx_rel).startswith("projects/"):
            manifest["onnx_blob"] = f"{dest}{str(onnx_rel).lstrip('/')}"

        manifest.update(
            {
                "project_id": project_id,
                "job_id": job_id,
                "task_type": item.task_type,
                "marketplace_item_id": item.id,
                "marketplace_name": item.name,
                "source": "marketplace",
            }
        )
        if item.classes and not manifest.get("classes"):
            manifest["classes"] = item.classes

        self.projects.store.write_json(manifest_key, manifest)

        if not self.projects.store.exists(weights_key):
            raise FileNotFoundError(f"Model weights missing after import at {weights_key}")

        return manifest


_import_service: MarketplaceImportService | None = None


def get_marketplace_import_service() -> MarketplaceImportService:
    global _import_service
    if _import_service is None:
        _import_service = MarketplaceImportService()
    return _import_service
