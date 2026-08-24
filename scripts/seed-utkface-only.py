#!/usr/bin/env python3
"""Seed only UTKFace-age marketplace dataset to blob + update catalog."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"
sys.path.insert(0, str(API_DIR))

from storage.blob_store import get_blob_store  # noqa: E402

CATALOG_PATH = API_DIR / "data" / "marketplace" / "catalog.json"
CATALOG_KEY = "marketplace/catalog.json"


def _load_seed_module():
    path = REPO_ROOT / "scripts" / "seed-marketplace.py"
    spec = importlib.util.spec_from_file_location("seed_marketplace", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    seed = _load_seed_module()
    store = get_blob_store()
    prefix = "marketplace/datasets/utkface-age/"
    print("=== UTKFace-only seed ===")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "utkface"
        n = seed._try_download_utkface(root)
        if not n:
            raise SystemExit("UTKFace download failed — blob left unchanged")
        seed._clear_blob_prefix(store, prefix)
        seed._upload_dir(store, root, prefix)
        print(f"Uploaded {n} images")

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for ds in catalog.get("datasets", []):
        if ds.get("id") == "utkface-age":
            ds["image_count"] = n
            ds["name"] = "UTKFace Age"
            ds["description"] = (
                "Aligned face portraits with age in years — full UTKFace-Cropped set for regression."
            )
            break
    catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    store.write_json(CATALOG_KEY, catalog)
    print(f"Catalog updated: utkface-age -> {n}")


if __name__ == "__main__":
    main()
