#!/usr/bin/env python3
"""Wait for main seed to finish, then sync catalog and fix UTKFace if overwritten."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"
sys.path.insert(0, str(API_DIR))

from storage.blob_store import get_blob_store  # noqa: E402

CATALOG_PATH = API_DIR / "data" / "marketplace" / "catalog.json"
CATALOG_KEY = "marketplace/catalog.json"
SEED_PID = int(os.environ.get("SEED_PID", "4544"))


def _load_seed():
    path = REPO_ROOT / "scripts" / "seed-marketplace.py"
    spec = importlib.util.spec_from_file_location("seed_marketplace", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _run_sync() -> None:
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "sync-marketplace-catalog.py")],
        check=True,
        env=os.environ.copy(),
    )


def _utkface_count(catalog: dict) -> int:
    for ds in catalog.get("datasets", []):
        if ds.get("id") == "utkface-age":
            return int(ds.get("image_count") or 0)
    return 0


def _fix_utkface_if_needed() -> None:
    store = get_blob_store()
    catalog = store.read_json(CATALOG_KEY)
    if not isinstance(catalog, dict):
        return
    if _utkface_count(catalog) >= 5000:
        print(f"UTKFace OK ({_utkface_count(catalog)} images)")
        return
    print("UTKFace count low — re-seeding full UTKFace…")
    seed = _load_seed()
    prefix = "marketplace/datasets/utkface-age/"
    seed._clear_blob_prefix(store, prefix)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "utkface"
        n = seed._try_download_utkface(root)
        if not n:
            print("UTKFace re-seed failed")
            return
        seed._upload_dir(store, root, prefix)
    for ds in catalog.get("datasets", []):
        if ds.get("id") == "utkface-age":
            ds["image_count"] = n
            break
    catalog["updated_at"] = datetime.now(timezone.utc).isoformat()
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    store.write_json(CATALOG_KEY, catalog)
    print(f"UTKFace restored: {n} images")


def main() -> None:
    print(f"Waiting for seed pid {SEED_PID}…")
    while True:
        try:
            os.kill(SEED_PID, 0)
        except OSError:
            break
        time.sleep(30)
    print("Main seed finished. Syncing catalog…")
    _run_sync()
    _fix_utkface_if_needed()
    _run_sync()
    print("Marketplace finalize complete.")


if __name__ == "__main__":
    main()
