#!/usr/bin/env python3
"""Sync marketplace catalog image_count / size from actual blob storage."""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"
sys.path.insert(0, str(API_DIR))

from storage.blob_store import get_blob_store  # noqa: E402

CATALOG_PATH = API_DIR / "data" / "marketplace" / "catalog.json"
CATALOG_KEY = "marketplace/catalog.json"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_size(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} GB"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.0f} KB"
    return f"{n} B"


def _count_zip_images(raw: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            return sum(
                1
                for name in zf.namelist()
                if name.lower().endswith(IMAGE_EXTS) and not name.endswith("/")
            )
    except zipfile.BadZipFile:
        return 0


def _count_loose_images(store, prefix: str) -> int:
    src = prefix.rstrip("/") + "/"
    count = 0
    for key in store.list_prefix(src):
        rel = key[len(src) :] if key.startswith(src) else ""
        if rel and "/" in rel and rel.lower().endswith(IMAGE_EXTS):
            count += 1
    return count


def _probe_dataset(store, storage_prefix: str, task_type: str) -> tuple[int, int]:
    """Return (image_count, size_bytes)."""
    src = storage_prefix.rstrip("/") + "/"
    total_size = 0
    image_count = 0

    zip_key = f"{src}classification.zip"
    raw = store.read_bytes(zip_key)
    if raw:
        total_size += len(raw)
        image_count = _count_zip_images(raw)
        if image_count:
            return image_count, total_size

    for key in store.list_prefix(src):
        if key.lower().endswith(".zip"):
            raw = store.read_bytes(key)
            if not raw:
                continue
            total_size += len(raw)
            n = _count_zip_images(raw)
            if n:
                return n, total_size

    for key in store.list_prefix(src):
        if key.lower().endswith(IMAGE_EXTS):
            data = store.read_bytes(key)
            if data:
                total_size += len(data)
                image_count += 1

    if image_count == 0 and task_type in ("multi_label", "regression"):
        image_count = _count_loose_images(store, src)
        for key in store.list_prefix(src):
            data = store.read_bytes(key)
            if data:
                total_size += len(data)

    return image_count, total_size


def main() -> None:
    store = get_blob_store()
    print(f"Storage backend: {store.backend} (container={store.container})")

    raw = store.read_json(CATALOG_KEY)
    if not isinstance(raw, dict):
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    catalog = raw
    catalog["updated_at"] = _now()

    print("\n=== Syncing dataset counts from blob ===")
    for ds in catalog.get("datasets", []):
        ds_id = ds.get("id", "?")
        prefix = ds.get("storage_prefix", "")
        task = ds.get("task_type", "")
        if not prefix:
            continue
        count, size = _probe_dataset(store, prefix, task)
        old = ds.get("image_count", 0)
        if count > 0:
            ds["image_count"] = count
            if size > 0:
                ds["size_bytes"] = size
                ds["size_label"] = _format_size(size)
            print(f"  {ds_id}: {old} -> {count} images ({ds.get('size_label', '?')})")
        else:
            print(f"  {ds_id}: no images found under {prefix}")

    CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    store.write_json(CATALOG_KEY, catalog)
    print(f"\nCatalog updated locally and at {CATALOG_KEY}")


if __name__ == "__main__":
    main()
