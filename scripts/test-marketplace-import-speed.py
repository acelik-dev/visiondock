#!/usr/bin/env python3
"""Time marketplace import API response (should return in <3s)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

# Load api/.env if present
env_file = ROOT / "api" / ".env"
if env_file.is_file():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from services.marketplace_import import MarketplaceImportService
from services.project_store import ProjectStore


def main() -> None:
    store = ProjectStore()
    meta = store.create("speed-test-imagenette")
    project_id = meta["id"]
    print(f"project_id={project_id}")

    svc = MarketplaceImportService()
    t0 = time.perf_counter()
    result = svc.import_dataset(project_id, "imagenette-160")
    elapsed = time.perf_counter() - t0
    print(f"import_dataset returned in {elapsed:.2f}s")
    print(f"import_status={result.get('import_status')}")
    print(f"task_type={result.get('task_type')}")

    if elapsed > 5.0:
        print("FAIL: response too slow (>5s)")
        sys.exit(1)

    # Wait for background job (max 180s)
    deadline = time.time() + 180
    while time.time() < deadline:
        meta = store.get_meta(project_id) or {}
        ds = meta.get("dataset") or {}
        status = ds.get("import_status")
        validated = ds.get("validated")
        if status == "completed" and validated:
            total = sum((ds.get("classes") or {}).get(c, {}).get("count", 0) for c in (ds.get("classes") or {}))
            print(f"background import done validated={validated} classes={len(ds.get('classes') or {})}")
            break
        time.sleep(2)
    else:
        ds = (store.get_meta(project_id) or {}).get("dataset") or {}
        print(f"WARN: background not finished in 180s import_status={ds.get('import_status')} validated={ds.get('validated')}")
        sys.exit(1)

    print("OK")


if __name__ == "__main__":
    main()
