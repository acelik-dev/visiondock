"""Read marketplace catalog and list/get datasets and models from blob storage."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from schemas.marketplace import (
    MarketplaceCatalog,
    MarketplaceDatasetItem,
    MarketplaceModelItem,
    SUPPORTED_TASK_TYPES,
)
from storage.blob_store import BlobStore, get_blob_store

CATALOG_KEY = "marketplace/catalog.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_MAX_PREVIEWS = 8
_THUMB_MAX_PX = 320
_catalog_cache: tuple[str | None, MarketplaceCatalog] | None = None


def _local_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "marketplace" / "catalog.json"


class MarketplaceStore:
    def __init__(self, store: BlobStore | None = None) -> None:
        self.store = store or get_blob_store()

    def _read_raw_catalog(self) -> dict | None:
        data = self.store.read_json(CATALOG_KEY)
        if isinstance(data, dict):
            return data
        local = _local_catalog_path()
        if local.is_file():
            return json.loads(local.read_text(encoding="utf-8"))
        return None

    def get_catalog(self, *, refresh: bool = False) -> MarketplaceCatalog:
        global _catalog_cache
        raw = self._read_raw_catalog()
        if not raw:
            _catalog_cache = (None, MarketplaceCatalog())
            return _catalog_cache[1]
        updated_at = raw.get("updated_at")
        if _catalog_cache is not None and not refresh:
            cached_at, cached = _catalog_cache
            if cached_at == updated_at:
                return cached
        catalog = MarketplaceCatalog.model_validate(raw)
        catalog.datasets = [d for d in catalog.datasets if d.task_type in SUPPORTED_TASK_TYPES]
        catalog.models = [m for m in catalog.models if m.task_type in SUPPORTED_TASK_TYPES]
        _catalog_cache = (updated_at, catalog)
        return catalog

    def list_datasets(
        self,
        task_type: str | None = None,
        industry: str | None = None,
    ) -> list[MarketplaceDatasetItem]:
        items = self.get_catalog().datasets
        if task_type:
            items = [d for d in items if d.task_type == task_type]
        if industry:
            want = industry.strip().lower()
            items = [
                d
                for d in items
                if any(str(x).strip().lower() == want for x in (d.industries or []))
            ]
        return items

    def list_models(
        self,
        task_type: str | None = None,
        industry: str | None = None,
    ) -> list[MarketplaceModelItem]:
        items = self.get_catalog().models
        if task_type:
            items = [m for m in items if m.task_type == task_type]
        if industry:
            want = industry.strip().lower()
            items = [
                m
                for m in items
                if any(str(x).strip().lower() == want for x in (m.industries or []))
            ]
        return items

    def get_dataset(self, item_id: str) -> MarketplaceDatasetItem | None:
        for item in self.get_catalog().datasets:
            if item.id == item_id:
                return item
        return None

    def get_model(self, item_id: str) -> MarketplaceModelItem | None:
        for item in self.get_catalog().models:
            if item.id == item_id:
                return item
        return None

    def item_exists_in_storage(self, storage_prefix: str) -> bool:
        prefix = storage_prefix.rstrip("/") + "/"
        for name in (
            "classification.zip",
            "voc_detection.zip",
            "dataset.zip",
            "model.json",
            "best.pt",
        ):
            if self.store.exists(f"{prefix}{name}"):
                return True
        keys = self.store.list_prefix(prefix)
        return len(keys) > 0

    def _preview_prefix(self, storage_prefix: str) -> str:
        return storage_prefix.rstrip("/") + "/previews/"

    def _get_dataset_by_id(self, item_id: str) -> MarketplaceDatasetItem | None:
        return self.get_dataset(item_id)

    def list_dataset_preview_names(self, item_id: str) -> list[str]:
        item = self._get_dataset_by_id(item_id)
        if item is None:
            return []
        prefix = self._preview_prefix(item.storage_prefix)
        names: list[str] = []
        for key in self.store.list_prefix(prefix):
            if not key.startswith(prefix):
                continue
            rel = key[len(prefix) :]
            if rel and "/" not in rel and _is_image_name(rel):
                names.append(rel)
        return sorted(names)

    def read_dataset_preview(self, item_id: str, filename: str) -> tuple[bytes, str] | None:
        item = self._get_dataset_by_id(item_id)
        if item is None:
            return None
        if not _safe_preview_filename(filename):
            return None
        key = f"{self._preview_prefix(item.storage_prefix)}{filename}"
        raw = self.store.read_bytes(key)
        if raw is None:
            self.ensure_dataset_previews(item)
            raw = self.store.read_bytes(key)
        if raw is None:
            return None
        return raw, _content_type_for_name(filename)

    def ensure_dataset_previews(self, item: MarketplaceDatasetItem) -> list[str]:
        existing = self.list_dataset_preview_names(item.id)
        if existing:
            return existing
        samples = self._collect_sample_images(item)
        if not samples:
            return []
        prefix = self._preview_prefix(item.storage_prefix)
        uploaded: list[str] = []
        for idx, (name, data) in enumerate(samples[:_MAX_PREVIEWS]):
            ext = Path(name).suffix.lower() or ".jpg"
            if ext not in _IMAGE_EXTS:
                ext = ".jpg"
            thumb, content_type = _make_thumbnail(data, ext)
            fname = f"{idx:02d}{ext if ext != '.jpeg' else '.jpg'}"
            self.store.write_bytes(f"{prefix}{fname}", thumb, content_type)
            uploaded.append(fname)
        return uploaded

    def _collect_sample_images(self, item: MarketplaceDatasetItem) -> list[tuple[str, bytes]]:
        src = item.storage_prefix.rstrip("/") + "/"
        samples: list[tuple[str, bytes]] = []

        zip_key = f"{src}classification.zip"
        raw = self.store.read_bytes(zip_key)
        if raw:
            samples.extend(_sample_images_from_zip(raw, _MAX_PREVIEWS * 3))
            if len(samples) >= _MAX_PREVIEWS:
                return _pick_spread(samples, _MAX_PREVIEWS)

        for key in self.store.list_prefix(src):
            if key.lower().endswith(".zip") and not key.endswith("classification.zip"):
                zraw = self.store.read_bytes(key)
                if zraw:
                    samples.extend(_sample_images_from_zip(zraw, _MAX_PREVIEWS * 3))
                    if len(samples) >= _MAX_PREVIEWS:
                        return _pick_spread(samples, _MAX_PREVIEWS)

        for key in self.store.list_prefix(src):
            rel = key[len(src) :] if key.startswith(src) else key
            if not rel or "/" not in rel:
                continue
            if _is_image_name(rel):
                data = self.store.read_bytes(key)
                if data:
                    samples.append((rel, data))
                    if len(samples) >= _MAX_PREVIEWS * 3:
                        break

        return _pick_spread(samples, _MAX_PREVIEWS)

    def get_dataset_preview_payload(self, item_id: str) -> dict | None:
        item = self.get_dataset(item_id)
        if item is None:
            return None
        previews = self.ensure_dataset_previews(item)
        return {**item.model_dump(), "previews": previews}

    def get_model_preview_payload(self, item_id: str) -> dict | None:
        item = self.get_model(item_id)
        if item is None:
            return None
        previews: list[str] = []
        classes = list(item.classes)
        dataset_id = item.trained_on
        if dataset_id:
            ds = self.get_dataset(dataset_id)
            if ds is not None:
                previews = self.ensure_dataset_previews(ds)
                if ds.classes:
                    classes = list(ds.classes)
        return {
            **item.model_dump(),
            "previews": previews,
            "classes": classes,
            "preview_dataset_id": dataset_id,
        }


def _safe_preview_filename(filename: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-zA-Z._-]+", filename)) and _is_image_name(filename)


def _is_image_name(name: str) -> bool:
    return Path(name.lower()).suffix in _IMAGE_EXTS


def _content_type_for_name(name: str) -> str:
    ext = Path(name.lower()).suffix
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "application/octet-stream")


def _make_thumbnail(data: bytes, ext: str) -> tuple[bytes, str]:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img.thumbnail((_THUMB_MAX_PX, _THUMB_MAX_PX), Image.Resampling.LANCZOS)
        out_ext = ext if ext in _IMAGE_EXTS else ".jpg"
        if out_ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        if out_ext in (".jpg", ".jpeg"):
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue(), "image/jpeg"
        if out_ext == ".png":
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), "image/png"
        if out_ext == ".webp":
            img.save(buf, format="WEBP", quality=85)
            return buf.getvalue(), "image/webp"
        img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, _content_type_for_name(f"x{ext}")


def _sample_images_from_zip(raw: bytes, limit: int) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if _is_image_name(n) and not n.endswith("/")]
            if len(names) > limit:
                step = max(1, len(names) // limit)
                names = names[::step][:limit]
            for name in names:
                try:
                    out.append((name, zf.read(name)))
                except (KeyError, RuntimeError):
                    continue
                if len(out) >= limit:
                    break
    except zipfile.BadZipFile:
        pass
    return out


def _pick_spread(samples: list[tuple[str, bytes]], limit: int) -> list[tuple[str, bytes]]:
    if len(samples) <= limit:
        return samples
    if limit <= 1:
        return samples[:1]
    step = len(samples) / limit
    indices = [int(i * step) for i in range(limit)]
    return [samples[i] for i in indices]


_marketplace_store: MarketplaceStore | None = None


def get_marketplace_store() -> MarketplaceStore:
    global _marketplace_store
    if _marketplace_store is None:
        _marketplace_store = MarketplaceStore()
    return _marketplace_store
