#!/usr/bin/env python3
"""Expand marketplace catalog with extra public datasets (Ultralytics, Oxford Pets, …).

Usage:
  export STORAGE_BACKEND=azure
  export AZURE_STORAGE_CONNECTION_STRING=...
  python3 scripts/seed-marketplace-more.py
"""

from __future__ import annotations

import gzip
import json
import os
import pickle
import struct
import sys
import tarfile
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

EXTRA = Path.home() / "Desktop" / "marketplace-extra-datasets"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


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
        s = line.strip()
        if s.startswith("names:"):
            rest = s.split(":", 1)[1].strip()
            if rest.startswith("["):
                return [p.strip().strip("'\"") for p in rest.strip("[]").split(",") if p.strip()]
            if rest.startswith("{"):
                # inline dict skipped
                continue
            in_names = True
            continue
        if in_names:
            if ":" in line and (line.startswith(" ") or line.startswith("\t") or line[:1].isdigit()):
                # "  0: buffalo" or "  buffalo:"
                left, right = line.split(":", 1)
                left, right = left.strip(), right.strip().strip("'\"")
                if left.isdigit():
                    names.append(right)
                elif right == "" or right.startswith("#"):
                    names.append(left)
                else:
                    names.append(left)
            elif s.startswith("-"):
                names.append(s.lstrip("-").strip().strip("'\""))
            elif s and not s.startswith("#"):
                break
    return names


def _seg_or_bbox_to_yolo_bbox(line: str) -> str | None:
    """Convert YOLO detect or seg polygon line → class cx cy w h."""
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        cls = int(float(parts[0]))
        nums = [float(x) for x in parts[1:]]
    except ValueError:
        return None
    if len(nums) == 4:
        return f"{cls} {nums[0]:.6f} {nums[1]:.6f} {nums[2]:.6f} {nums[3]:.6f}"
    # polygon: x1 y1 x2 y2 …
    xs = nums[0::2]
    ys = nums[1::2]
    if not xs or not ys or len(xs) != len(ys):
        return None
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def _collect_pairs(ds_root: Path) -> list[tuple[Path, Path]]:
    """Support train/images and images/train layouts (+ export)."""
    pairs: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    layouts = []
    for split in ("train", "valid", "val", "test", "export"):
        layouts.append((ds_root / split / "images", ds_root / split / "labels"))
        layouts.append((ds_root / "images" / split, ds_root / "labels" / split))
    # flat images/ + labels/
    layouts.append((ds_root / "images", ds_root / "labels"))

    for img_dir, lbl_dir in layouts:
        if not img_dir.is_dir():
            continue
        for img in img_dir.rglob("*"):
            if not img.is_file() or img.suffix.lower() not in IMG_EXTS:
                continue
            lbl = lbl_dir / f"{img.stem}.txt"
            if not lbl.is_file():
                # sometimes labels nest differently
                candidates = list(lbl_dir.rglob(f"{img.stem}.txt"))
                if not candidates:
                    continue
                lbl = candidates[0]
            key = str(img.resolve())
            if key in seen:
                continue
            seen.add(key)
            pairs.append((img, lbl))
    return pairs


def _zip_yolo(ds_root: Path, zip_path: Path, max_images: int = 3000, convert_seg: bool = False) -> tuple[int, list[str]]:
    yaml_files = list(ds_root.glob("*.yaml")) + list(ds_root.glob("*.yml"))
    classes: list[str] = []
    for y in yaml_files:
        classes = _parse_yaml_names(y)
        if classes:
            break
    pairs = _collect_pairs(ds_root)
    if max_images and len(pairs) > max_images:
        pairs = pairs[:max_images]
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, (img, lbl) in enumerate(pairs):
            lines_out: list[str] = []
            for line in lbl.read_text(encoding="utf-8", errors="ignore").splitlines():
                if convert_seg:
                    bb = _seg_or_bbox_to_yolo_bbox(line)
                else:
                    bb = _seg_or_bbox_to_yolo_bbox(line)  # also normalizes detect
                if bb:
                    lines_out.append(bb)
            if not lines_out and convert_seg:
                continue
            stem = f"img_{i:05d}{img.suffix.lower()}"
            zf.write(img, f"images/{stem}")
            zf.writestr(f"labels/{Path(stem).stem}.txt", "\n".join(lines_out) + ("\n" if lines_out else ""))
            kept += 1
        if classes:
            zf.writestr("classes.txt", "\n".join(classes) + "\n")
    return kept, classes


def _zip_oxford_pets(pets_root: Path, zip_path: Path, max_per_class: int = 40) -> tuple[int, list[str]]:
    img_dir = pets_root / "images"
    by_class: dict[str, list[Path]] = {}
    for img in img_dir.iterdir():
        if img.suffix.lower() not in IMG_EXTS:
            continue
        # Abyssinian_1.jpg → Abyssinian
        name = img.stem.rsplit("_", 1)[0]
        by_class.setdefault(name, []).append(img)
    classes = sorted(by_class)
    total = 0
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for cls in classes:
            for i, img in enumerate(by_class[cls][:max_per_class]):
                zf.write(img, f"{cls}/{cls}_{i:04d}{img.suffix.lower()}")
                total += 1
    return total, classes


def _zip_mnist(images_gz: Path, labels_gz: Path, zip_path: Path, max_per_class: int = 200) -> tuple[int, list[str]]:
    with gzip.open(images_gz, "rb") as f:
        magic, n, rows, cols = struct.unpack(">IIII", f.read(16))
        raw = f.read()
    with gzip.open(labels_gz, "rb") as f:
        magic_l, n_l = struct.unpack(">II", f.read(8))
        labels = list(f.read())
    classes = [str(i) for i in range(10)]
    counts = {i: 0 for i in range(10)}
    total = 0
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    import io as bio

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx in range(min(n, len(labels))):
            lab = labels[idx]
            if counts[lab] >= max_per_class:
                if all(c >= max_per_class for c in counts.values()):
                    break
                continue
            start = idx * rows * cols
            buf = raw[start : start + rows * cols]
            img = Image.frombytes("L", (cols, rows), buf)
            out = bio.BytesIO()
            img.save(out, format="PNG")
            zf.writestr(f"{lab}/{lab}_{counts[lab]:04d}.png", out.getvalue())
            counts[lab] += 1
            total += 1
    return total, classes


def _zip_cifar100(tgz: Path, zip_path: Path, max_per_class: int = 20) -> tuple[int, list[str]]:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(tgz) as tar:
            tar.extractall(tmp)
        # find meta + train
        meta = next(Path(tmp).rglob("meta"))
        train = next(Path(tmp).rglob("train"))
        with open(meta, "rb") as f:
            meta_d = pickle.load(f, encoding="latin1")
        fine = [x.decode() if isinstance(x, bytes) else x for x in meta_d["fine_label_names"]]
        with open(train, "rb") as f:
            data = pickle.load(f, encoding="latin1")
        labels = data["fine_labels"]
        images = data["data"]  # N x 3072
        counts = {i: 0 for i in range(100)}
        total = 0
        from PIL import Image
        import io as bio
        import numpy as np

        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, lab in enumerate(labels):
                if counts[lab] >= max_per_class:
                    if all(c >= max_per_class for c in counts.values()):
                        break
                    continue
                arr = images[idx].reshape(3, 32, 32).transpose(1, 2, 0)
                img = Image.fromarray(arr)
                out = bio.BytesIO()
                img.save(out, format="PNG")
                name = fine[lab].replace("/", "_")
                zf.writestr(f"{name}/{name}_{counts[lab]:04d}.png", out.getvalue())
                counts[lab] += 1
                total += 1
        return total, [x.replace("/", "_") for x in fine]


def _zip_stl10(tgz: Path, zip_path: Path, max_per_class: int = 200) -> tuple[int, list[str]]:
    import tempfile
    import numpy as np
    from PIL import Image
    import io as bio

    classes = ["airplane", "bird", "car", "cat", "deer", "dog", "horse", "monkey", "ship", "truck"]
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(tgz) as tar:
            tar.extractall(tmp)
        root = next(Path(tmp).rglob("train_X.bin")).parent
        x = np.fromfile(root / "train_X.bin", dtype=np.uint8).reshape(-1, 3, 96, 96)
        y = np.fromfile(root / "train_y.bin", dtype=np.uint8)  # 1..10
        counts = {i: 0 for i in range(1, 11)}
        total = 0
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx in range(len(y)):
                lab = int(y[idx])
                if counts[lab] >= max_per_class:
                    if all(c >= max_per_class for c in counts.values()):
                        break
                    continue
                arr = np.transpose(x[idx], (1, 2, 0))
                img = Image.fromarray(arr)
                out = bio.BytesIO()
                img.save(out, format="PNG")
                name = classes[lab - 1]
                zf.writestr(f"{name}/{name}_{counts[lab]:04d}.png", out.getvalue())
                counts[lab] += 1
                total += 1
        return total, classes


def _zip_gtsrb(zip_in: Path, zip_path: Path, max_per_class: int = 40) -> tuple[int, list[str]]:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_in) as z:
            z.extractall(tmp)
        # GTSRB/Final_Training/Images/00000/*.ppm
        base = next(Path(tmp).rglob("Final_Training"), None)
        if base is None:
            base = next(Path(tmp).rglob("Images"), None)
        if base is None:
            raise FileNotFoundError("GTSRB Images not found")
        img_root = base / "Images" if (base / "Images").is_dir() else base
        classes: list[str] = []
        total = 0
        from PIL import Image
        import io as bio

        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for cls_dir in sorted(p for p in img_root.iterdir() if p.is_dir()):
                cls = cls_dir.name
                classes.append(cls)
                imgs = [p for p in cls_dir.iterdir() if p.suffix.lower() in {".ppm", ".png", ".jpg", ".jpeg"}]
                for i, img_path in enumerate(imgs[:max_per_class]):
                    img = Image.open(img_path).convert("RGB")
                    out = bio.BytesIO()
                    img.save(out, format="JPEG", quality=85)
                    zf.writestr(f"{cls}/{cls}_{i:04d}.jpg", out.getvalue())
                    total += 1
        return total, classes


def _upsert(catalog: MarketplaceCatalog, item: MarketplaceDatasetItem) -> None:
    catalog.datasets = [d for d in catalog.datasets if d.id != item.id]
    catalog.datasets.append(item)


def _upload(store, key: str, path: Path) -> None:
    store.write_bytes(key, path.read_bytes(), content_type="application/zip")


SPECS: list[dict] = [
    {
        "id": "ultra-african-wildlife",
        "name": "African Wildlife",
        "task_type": "object_detection",
        "industries": ["Agriculture", "Sports"],
        "description": "Buffalo, elephant, rhino, zebra detection (Ultralytics).",
        "license": "AGPL-3.0",
        "source_url": "https://docs.ultralytics.com/datasets/detect/african-wildlife/",
        "kind": "yolo_folder",
        "path": EXTRA / "african-wildlife",
    },
    {
        "id": "ultra-signature",
        "name": "Signatures",
        "task_type": "object_detection",
        "industries": ["Documents"],
        "description": "Signature detection on documents (Ultralytics).",
        "license": "AGPL-3.0",
        "source_url": "https://docs.ultralytics.com/datasets/detect/signature/",
        "kind": "yolo_folder",
        "path": EXTRA / "signature",
    },
    {
        "id": "ultra-brain-tumor",
        "name": "Brain Tumor",
        "task_type": "object_detection",
        "industries": ["Manufacturing", "Documents"],
        "description": "Brain MRI tumor region detection (Ultralytics).",
        "license": "AGPL-3.0",
        "source_url": "https://docs.ultralytics.com/datasets/detect/brain-tumor/",
        "kind": "yolo_folder",
        "path": EXTRA / "brain-tumor",
    },
    {
        "id": "ultra-package-boxes",
        "name": "Package Boxes",
        "task_type": "object_detection",
        "industries": ["Logistics", "Manufacturing"],
        "description": "Parcel / package box detection (converted from package-seg).",
        "license": "AGPL-3.0",
        "source_url": "https://docs.ultralytics.com/datasets/segment/package-seg/",
        "kind": "yolo_seg_folder",
        "path": EXTRA / "package-seg",
    },
    {
        "id": "ultra-crack-detection",
        "name": "Crack Detection",
        "task_type": "object_detection",
        "industries": ["Construction", "Manufacturing"],
        "description": "Surface crack detection for infrastructure inspection (from crack-seg).",
        "license": "AGPL-3.0",
        "source_url": "https://docs.ultralytics.com/datasets/segment/crack-seg/",
        "kind": "yolo_seg_folder",
        "path": EXTRA / "crack-seg",
    },
    {
        "id": "ultra-car-parts",
        "name": "Car Parts",
        "task_type": "object_detection",
        "industries": ["Self Driving", "Manufacturing", "Logistics"],
        "description": "Automotive part detection (doors, wheels, lights…) from carparts-seg.",
        "license": "AGPL-3.0",
        "source_url": "https://docs.ultralytics.com/datasets/segment/carparts-seg/",
        "kind": "yolo_seg_folder",
        "path": EXTRA / "carparts-seg",
    },
    {
        "id": "oxford-pets",
        "name": "Oxford-IIIT Pets",
        "task_type": "classification",
        "industries": ["Agriculture", "Gaming"],
        "description": "37 cat & dog breed classification (Oxford-IIIT).",
        "license": "CC BY-SA 4.0",
        "source_url": "https://www.robots.ox.ac.uk/~vgg/data/pets/",
        "kind": "oxford_pets",
        "path": EXTRA / "oxford-pets",
    },
    {
        "id": "stl-10",
        "name": "STL-10",
        "task_type": "classification",
        "industries": ["Self Driving", "Logistics", "Agriculture"],
        "description": "10-class natural image classification (airplane, car, truck, animals…).",
        "license": "Research",
        "source_url": "https://cs.stanford.edu/~acoates/stl10/",
        "kind": "stl10",
        "path": EXTRA / "hf" / "stl10_binary.tar.gz",
    },
    {
        "id": "mnist-digits",
        "name": "MNIST Digits",
        "task_type": "classification",
        "industries": ["Documents", "Gaming"],
        "description": "Handwritten digit classification 0–9.",
        "license": "Public Domain",
        "source_url": "http://yann.lecun.com/exdb/mnist/",
        "kind": "mnist",
        "path": EXTRA / "hf",
    },
    {
        "id": "cifar-100",
        "name": "CIFAR-100",
        "task_type": "classification",
        "industries": ["Gaming", "Agriculture", "Documents"],
        "description": "100 fine-grained object categories (subset per class).",
        "license": "Research",
        "source_url": "https://www.cs.toronto.edu/~kriz/cifar.html",
        "kind": "cifar100",
        "path": EXTRA / "hf" / "cifar-100-python.tar.gz",
    },
    {
        "id": "gtsrb-signs",
        "name": "GTSRB Traffic Signs",
        "task_type": "classification",
        "industries": ["Self Driving", "Logistics"],
        "description": "German Traffic Sign Recognition Benchmark — road sign classes.",
        "license": "CC0",
        "source_url": "https://benchmark.ini.rub.de/gtsrb_dataset.html",
        "kind": "gtsrb",
        "path": EXTRA / "hf" / "gtsrb_train.zip",
    },
]


def main() -> int:
    store = get_blob_store()
    mstore = get_marketplace_store()
    catalog = mstore.get_catalog(refresh=True)
    work = Path(os.getenv("MARKETPLACE_SEED_WORK", str(ROOT / "tmp" / "marketplace-more")))
    work.mkdir(parents=True, exist_ok=True)

    imported = 0
    for spec in SPECS:
        path: Path = spec["path"]
        ds_id = spec["id"]
        print(f"IMPORT {ds_id} ({spec['kind']})")
        try:
            local = work / ds_id
            local.mkdir(parents=True, exist_ok=True)
            kind = spec["kind"]
            if kind == "yolo_folder":
                if not path.is_dir():
                    print("  SKIP missing", path)
                    continue
                zip_path = local / "voc_detection.zip"
                n, classes = _zip_yolo(path, zip_path)
                blob = "voc_detection.zip"
                fmt = "yolo"
            elif kind == "yolo_seg_folder":
                if not path.is_dir():
                    print("  SKIP missing", path)
                    continue
                zip_path = local / "voc_detection.zip"
                n, classes = _zip_yolo(path, zip_path, convert_seg=True)
                blob = "voc_detection.zip"
                fmt = "yolo"
            elif kind == "oxford_pets":
                if not path.is_dir():
                    print("  SKIP missing", path)
                    continue
                zip_path = local / "classification.zip"
                n, classes = _zip_oxford_pets(path, zip_path)
                blob = "classification.zip"
                fmt = "classification-folders"
            elif kind == "stl10":
                if not path.is_file() or path.stat().st_size < 50_000_000:
                    print("  SKIP incomplete", path)
                    continue
                zip_path = local / "classification.zip"
                n, classes = _zip_stl10(path, zip_path)
                blob = "classification.zip"
                fmt = "classification-folders"
            elif kind == "mnist":
                img = path / "mnist-images.gz"
                lbl = path / "mnist-labels.gz"
                if not img.is_file() or not lbl.is_file():
                    print("  SKIP missing mnist")
                    continue
                zip_path = local / "classification.zip"
                n, classes = _zip_mnist(img, lbl, zip_path)
                blob = "classification.zip"
                fmt = "classification-folders"
            elif kind == "cifar100":
                if not path.is_file() or path.stat().st_size < 50_000_000:
                    print("  SKIP incomplete", path)
                    continue
                zip_path = local / "classification.zip"
                n, classes = _zip_cifar100(path, zip_path)
                blob = "classification.zip"
                fmt = "classification-folders"
            elif kind == "gtsrb":
                if not path.is_file() or path.stat().st_size < 1_000_000:
                    print("  SKIP incomplete", path)
                    continue
                zip_path = local / "classification.zip"
                n, classes = _zip_gtsrb(path, zip_path)
                blob = "classification.zip"
                fmt = "classification-folders"
            else:
                print("  SKIP unknown kind")
                continue

            if n <= 0:
                print("  FAIL empty")
                continue
            prefix = f"marketplace/datasets/{ds_id}/"
            key = f"{prefix}{blob}"
            _upload(store, key, zip_path)
            size = zip_path.stat().st_size
            item = MarketplaceDatasetItem(
                id=ds_id,
                name=spec["name"],
                task_type=spec["task_type"],
                description=spec["description"],
                license=spec["license"],
                storage_prefix=prefix,
                format=fmt,
                size_bytes=size,
                size_label=_human_size(size),
                image_count=n,
                class_count=len(classes),
                classes=classes[:80],
                tags=["public", *spec["industries"]],
                industries=[i for i in spec["industries"] if i in MARKETPLACE_INDUSTRIES],
                source_url=spec["source_url"],
                year=datetime.now(timezone.utc).year,
            )
            _upsert(catalog, item)
            imported += 1
            print(f"  OK {n} images / {len(classes)} classes → {key}")
        except Exception as exc:
            print(f"  FAIL {ds_id}: {exc}")

    catalog.updated_at = _now()
    catalog.version = "3"
    payload = json.loads(catalog.model_dump_json())
    store.write_json(CATALOG_KEY, payload)
    local_catalog = ROOT / "api" / "data" / "marketplace" / "catalog.json"
    local_catalog.parent.mkdir(parents=True, exist_ok=True)
    local_catalog.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    import services.marketplace_store as ms

    ms._catalog_cache = None
    by: dict[str, int] = {}
    for d in catalog.datasets:
        for i in d.industries or []:
            by[i] = by.get(i, 0) + 1
    print(f"\nImported {imported}. Total datasets: {len(catalog.datasets)}")
    print("Per industry:", by)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
