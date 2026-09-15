#!/usr/bin/env python3
"""Tag marketplace datasets with industries and import Roboflow Desktop downloads.

Usage (local storage):
  cd /path/to/AI-Model-Builder
  STORAGE_BACKEND=local \\
  LOCAL_STORAGE_PATH=./api/data/storage \\
  python3 scripts/seed-marketplace-industries.py

Optional Azure:
  STORAGE_BACKEND=azure AZURE_STORAGE_CONNECTION_STRING=... python3 scripts/seed-marketplace-industries.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from schemas.marketplace import (  # noqa: E402
    MARKETPLACE_INDUSTRIES,
    MarketplaceCatalog,
    MarketplaceDatasetItem,
)
from services.marketplace_store import CATALOG_KEY, get_marketplace_store  # noqa: E402
from storage.blob_store import get_blob_store  # noqa: E402

ROBOFLOW_DIR = Path.home() / "Desktop" / "roboflow-public-datasets"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Existing catalog ids → industries
EXISTING_INDUSTRIES: dict[str, list[str]] = {
    "imagenette-160": ["Documents"],
    "cifar-10": ["Gaming", "Documents"],
    "voc-2012-detection": ["Self Driving", "Logistics"],
    "voc-single-object": ["Self Driving", "Logistics"],
    "voc-multilabel": ["Logistics", "Agriculture"],
    "utkface-age": ["Documents"],
    "coco128-detection": ["Self Driving", "Logistics", "Sports"],
    "coco128-localization": ["Self Driving", "Logistics"],
    "coco128-multilabel": ["Logistics", "Agriculture"],
    "fashion-mnist": ["Logistics", "Documents"],
    "flowers-102": ["Agriculture"],
}

# Desktop Roboflow folders → marketplace entries
ROBOFLOW_IMPORTS: list[dict] = [
    {
        "folder": "aquarium",
        "id": "rf-aquarium",
        "name": "Aquarium Creatures",
        "task_type": "object_detection",
        "industries": ["Agriculture"],
        "description": "Fish, sharks, jellyfish and more — aquarium object detection (CC BY 4.0).",
        "license": "CC BY 4.0",
        "source_url": "https://universe.roboflow.com/brad-dwyer/aquarium-combined",
        "kind": "yolo",
    },
    {
        "folder": "hard-hat-workers",
        "id": "rf-hard-hat-workers",
        "name": "Hard Hat Workers",
        "task_type": "object_detection",
        "industries": ["Construction", "Manufacturing"],
        "description": "Heads, helmets, and people on construction sites (PPE detection).",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/hard-hat-workers",
        "kind": "yolo",
    },
    {
        "folder": "circuit-elements",
        "id": "rf-circuit-elements",
        "name": "Circuit Elements",
        "task_type": "object_detection",
        "industries": ["Manufacturing", "Documents"],
        "description": "PCB / schematic component detection (resistors, ICs, capacitors, …).",
        "license": "CC BY 4.0",
        "source_url": "https://universe.roboflow.com/roboflow-100/circuit-elements",
        "kind": "yolo",
    },
    {
        "folder": "chess-pieces",
        "id": "rf-chess-pieces",
        "name": "Chess Pieces",
        "task_type": "object_detection",
        "industries": ["Gaming"],
        "description": "Board-angle chess piece detection (king, queen, pawn, …).",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/chess-pieces-new",
        "kind": "yolo",
    },
    {
        "folder": "pistols",
        "id": "rf-pistols",
        "name": "Pistols Detection",
        "task_type": "object_detection",
        "industries": ["Sports"],
        "description": "Handgun object detection for safety / sports shooting demos.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/pistols",
        "kind": "yolo",
    },
    {
        "folder": "mask-wearing",
        "id": "rf-mask-wearing",
        "name": "Mask Wearing",
        "task_type": "object_detection",
        "industries": ["Construction", "Manufacturing"],
        "description": "Face-mask compliance detection in workplace settings.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/mask-wearing",
        "kind": "yolo",
    },
    {
        "folder": "thermal-cheetah",
        "id": "rf-thermal-cheetah",
        "name": "Thermal Cheetah",
        "task_type": "object_detection",
        "industries": ["Agriculture", "Manufacturing"],
        "description": "Thermal wildlife detection (cheetah).",
        "license": "CC BY 4.0",
        "source_url": "https://universe.roboflow.com/brad-dwyer/thermal-cheetah",
        "kind": "yolo",
    },
    {
        "folder": "uno-cards",
        "id": "rf-uno-cards",
        "name": "UNO Cards",
        "task_type": "object_detection",
        "industries": ["Gaming"],
        "description": "Playing-card detection for tabletop / gaming CV.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/uno-cards",
        "kind": "yolo",
    },
    {
        "folder": "egohands",
        "id": "rf-egohands",
        "name": "EgoHands",
        "task_type": "object_detection",
        "industries": ["Gaming", "Manufacturing"],
        "description": "Egocentric hand detection (left/right, self/other).",
        "license": "CC BY 4.0",
        "source_url": "https://universe.roboflow.com/brad-dwyer/egohands-public",
        "kind": "yolo",
    },
    {
        "folder": "boggle-boards",
        "id": "rf-boggle-boards",
        "name": "Boggle Boards",
        "task_type": "object_detection",
        "industries": ["Gaming", "Documents"],
        "description": "Letter-tile / board detection for puzzle games and OCR demos.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/boggle-boards",
        "kind": "yolo",
    },
    {
        "folder": "rock-paper-scissors",
        "id": "rf-rock-paper-scissors",
        "name": "Rock Paper Scissors",
        "task_type": "classification",
        "industries": ["Gaming"],
        "description": "Classic rock / paper / scissors image classification.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/rock-paper-scissors",
        "kind": "classification",
    },
    {
        "folder": "vehicles",
        "id": "rf-vehicles",
        "name": "Vehicles",
        "task_type": "object_detection",
        "industries": ["Self Driving", "Logistics"],
        "description": "Cars, trucks, and road vehicles for self-driving / logistics demos.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/vehicles-q0x2v",
        "kind": "yolo",
    },
    {
        "folder": "construction-safety",
        "id": "rf-construction-safety",
        "name": "Construction Site Safety",
        "task_type": "object_detection",
        "industries": ["Construction", "Manufacturing"],
        "description": "PPE and site hazards (helmets, vests, machinery) on construction sites.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/construction-site-safety",
        "kind": "yolo",
    },
    {
        "folder": "asl-letters",
        "id": "rf-asl-letters",
        "name": "ASL Letters",
        "task_type": "object_detection",
        "industries": ["Documents", "Gaming"],
        "description": "American Sign Language letter detection — OCR-adjacent gesture recognition.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/american-sign-language-letters",
        "kind": "yolo",
    },
    {
        "folder": "wildfire-smoke",
        "id": "rf-wildfire-smoke",
        "name": "Wildfire Smoke",
        "task_type": "object_detection",
        "industries": ["Agriculture", "Manufacturing"],
        "description": "Smoke plume detection for wildfire and industrial monitoring.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/wildfire-smoke",
        "kind": "yolo",
    },
    {
        "folder": "taco-trash",
        "id": "rf-taco-trash",
        "name": "TACO Trash",
        "task_type": "object_detection",
        "industries": ["Logistics", "Manufacturing"],
        "description": "Litter / waste object detection for recycling and city logistics.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/taco",
        "kind": "yolo",
    },
    {
        "folder": "aerial-maritime",
        "id": "rf-aerial-maritime",
        "name": "Aerial Maritime",
        "task_type": "object_detection",
        "industries": ["Logistics", "Self Driving"],
        "description": "Aerial maritime vessel / dock objects for logistics surveillance.",
        "license": "Public Domain",
        "source_url": "https://universe.roboflow.com/joseph-nelson/aerial-maritime",
        "kind": "yolo",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _human_size(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024 or unit == "GB":
            return f"{x:.0f} {unit}" if unit == "B" else f"{x:.1f} {unit}"
        x /= 1024
    return f"{n} B"


def _parse_yaml_names(yaml_path: Path) -> list[str]:
    names: list[str] = []
    in_names = False
    for line in yaml_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("names:"):
            rest = line.split(":", 1)[1].strip()
            if rest.startswith("["):
                # inline list
                rest = rest.strip("[]")
                return [p.strip().strip("'\"") for p in rest.split(",") if p.strip()]
            in_names = True
            continue
        if in_names:
            if line.startswith(" ") or line.startswith("-"):
                item = line.strip().lstrip("-").strip().strip("'\"")
                if item:
                    names.append(item)
            else:
                break
    return names


def _collect_yolo_pairs(ds_root: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for split in ("train", "valid", "val", "test", "export"):
        img_dir = ds_root / split / "images"
        lbl_dir = ds_root / split / "labels"
        if not img_dir.is_dir():
            continue
        for img in img_dir.rglob("*"):
            if img.suffix.lower() not in IMG_EXTS:
                continue
            lbl = lbl_dir / f"{img.stem}.txt"
            if lbl.is_file():
                pairs.append((img, lbl))
    return pairs


def _zip_yolo_dataset(ds_root: Path, zip_path: Path, max_images: int = 2500) -> tuple[int, list[str]]:
    yaml = ds_root / "data.yaml"
    classes = _parse_yaml_names(yaml) if yaml.is_file() else []
    pairs = _collect_yolo_pairs(ds_root)
    if max_images and len(pairs) > max_images:
        pairs = pairs[:max_images]
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, (img, lbl) in enumerate(pairs):
            stem = f"img_{i:05d}{img.suffix.lower()}"
            zf.write(img, f"images/{stem}")
            zf.write(lbl, f"labels/{Path(stem).stem}.txt")
        if classes:
            zf.writestr("classes.txt", "\n".join(classes) + "\n")
    return len(pairs), classes


def _zip_classification_dataset(ds_root: Path, zip_path: Path, max_per_class: int = 400) -> tuple[int, list[str]]:
    train = ds_root / "train"
    classes = sorted([p.name for p in train.iterdir() if p.is_dir()]) if train.is_dir() else []
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for cls in classes:
            imgs = [p for p in (train / cls).iterdir() if p.suffix.lower() in IMG_EXTS]
            for i, img in enumerate(imgs[:max_per_class]):
                zf.write(img, f"{cls}/{cls}_{i:04d}{img.suffix.lower()}")
                total += 1
    return total, classes


def _upload_file(store, key: str, path: Path) -> None:
    store.write_bytes(key, path.read_bytes(), content_type="application/zip")


def _upsert_dataset(catalog: MarketplaceCatalog, item: MarketplaceDatasetItem) -> None:
    catalog.datasets = [d for d in catalog.datasets if d.id != item.id]
    catalog.datasets.append(item)


def main() -> int:
    store = get_blob_store()
    mstore = get_marketplace_store()
    catalog = mstore.get_catalog(refresh=True)
    work = Path(os.getenv("MARKETPLACE_SEED_WORK", str(ROOT / "tmp" / "marketplace-industries")))
    work.mkdir(parents=True, exist_ok=True)

    # 1) Tag existing entries
    patched = 0
    new_datasets: list[MarketplaceDatasetItem] = []
    for d in catalog.datasets:
        industries = EXISTING_INDUSTRIES.get(d.id, list(d.industries or []))
        # Keep only known industries
        industries = [i for i in industries if i in MARKETPLACE_INDUSTRIES]
        data = d.model_dump()
        data["industries"] = industries
        new_datasets.append(MarketplaceDatasetItem.model_validate(data))
        if industries:
            patched += 1
    catalog.datasets = new_datasets
    print(f"Tagged existing datasets with industries: {patched}")

    # 2) Import Roboflow Desktop downloads
    imported = 0
    for spec in ROBOFLOW_IMPORTS:
        folder = ROBOFLOW_DIR / spec["folder"]
        if not folder.is_dir():
            print(f"SKIP missing {folder}")
            continue
        ds_id = spec["id"]
        prefix = f"marketplace/datasets/{ds_id}/"
        local_out = work / ds_id
        local_out.mkdir(parents=True, exist_ok=True)
        print(f"IMPORT {ds_id} from {folder}")
        try:
            if spec["kind"] == "yolo":
                zip_path = local_out / "voc_detection.zip"
                n, classes = _zip_yolo_dataset(folder, zip_path)
                blob_name = "voc_detection.zip"
            else:
                zip_path = local_out / "classification.zip"
                n, classes = _zip_classification_dataset(folder, zip_path)
                blob_name = "classification.zip"
            if n <= 0:
                print(f"  FAIL empty dataset {ds_id}")
                continue
            key = f"{prefix}{blob_name}"
            _upload_file(store, key, zip_path)
            size = zip_path.stat().st_size
            item = MarketplaceDatasetItem(
                id=ds_id,
                name=spec["name"],
                task_type=spec["task_type"],
                description=spec["description"],
                license=spec["license"],
                storage_prefix=prefix,
                format="yolo" if spec["kind"] == "yolo" else "classification-folders",
                size_bytes=size,
                size_label=_human_size(size),
                image_count=n,
                class_count=len(classes),
                classes=classes,
                tags=["roboflow", "universe", *spec["industries"]],
                industries=spec["industries"],
                source_url=spec["source_url"],
                year=datetime.now(timezone.utc).year,
            )
            _upsert_dataset(catalog, item)
            imported += 1
            print(f"  OK {n} images, {len(classes)} classes → {key}")
        except Exception as exc:
            print(f"  FAIL {ds_id}: {exc}")

    catalog.updated_at = _now()
    catalog.version = "2"
    payload = json.loads(catalog.model_dump_json())
    store.write_json(CATALOG_KEY, payload)

    local_catalog = ROOT / "api" / "data" / "marketplace" / "catalog.json"
    local_catalog.parent.mkdir(parents=True, exist_ok=True)
    local_catalog.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # invalidate cache
    import services.marketplace_store as ms

    ms._catalog_cache = None

    by_ind: dict[str, int] = {i: 0 for i in MARKETPLACE_INDUSTRIES}
    for d in catalog.datasets:
        for i in d.industries or []:
            by_ind[i] = by_ind.get(i, 0) + 1

    print(f"\nDone. Imported {imported} Roboflow datasets.")
    print(f"Catalog datasets: {len(catalog.datasets)}")
    print("Per industry:", {k: v for k, v in by_ind.items() if v})
    print(f"Wrote {CATALOG_KEY} + {local_catalog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
