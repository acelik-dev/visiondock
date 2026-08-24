#!/usr/bin/env python3
"""Seed VisionDock marketplace catalog + blob artifacts (local or Azure).

Usage:
  cd /path/to/AI-Model-Builder
  python scripts/seed-marketplace.py

Environment (optional):
  STORAGE_BACKEND=local|azure
  AZURE_STORAGE_CONNECTION_STRING=...
  AZURE_STORAGE_CONTAINER=visiondock
  LOCAL_STORAGE_PATH=api/data
  SEED_DOWNLOAD=1   # attempt real dataset downloads (slower, needs network)
"""

from __future__ import annotations

import pickle
import csv
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"
sys.path.insert(0, str(API_DIR))

from storage.blob_store import get_blob_store  # noqa: E402

CATALOG_PATH = API_DIR / "data" / "marketplace" / "catalog.json"
CATALOG_KEY = "marketplace/catalog.json"
IMAGENETTE_URL = "https://files.fast.ai/data/examples/imagenette2-160.tgz"
IMAGENETTE_URL_FALLBACK = "https://s3.amazonaws.com/fast-ai-imageclas/imagenette2-160.tgz"
CIFAR10_URL = "https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz"
VOC2012_URL = "http://host.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar"
VOC2012_FALLBACK_URL = "https://pjreddie.com/media/files/VOCtrainval_11-May-2012.tar"
UTKFACE_URL = "https://huggingface.co/datasets/py97/UTKFace-Cropped/resolve/main/UTKFace.tar.gz"
COCO128_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip"
YOLO_WEIGHTS_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"

COCO128_CLASSES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]


def _seed_per_class() -> int:
    """0 = full dataset (no per-class cap)."""
    raw = os.getenv("SEED_PER_CLASS", "0").strip().lower()
    if raw in ("0", "", "full", "all", "none"):
        return 0
    return max(5, int(raw))


def _resolve_per_class_limit(per_class_limit: int | None) -> int:
    if per_class_limit is None:
        return _seed_per_class()
    return per_class_limit


def _seed_image_count() -> int:
    raw = os.getenv("SEED_IMAGE_COUNT", "0").strip().lower()
    if raw in ("0", "", "full", "all"):
        return 0
    return max(10, int(raw))

IMAGENETTE_CLASSES = [
    "tench",
    "english_springer",
    "cassette_player",
    "chain_saw",
    "church",
    "french_horn",
    "garbage_truck",
    "gas_pump",
    "golf_ball",
    "parachute",
]

CIFAR10_CLASSES = [
    "airplane",
    "automobile",
    "bird",
    "cat",
    "deer",
    "dog",
    "frog",
    "horse",
    "ship",
    "truck",
]

VOC_CLASSES = [
    "aeroplane",
    "bicycle",
    "bird",
    "boat",
    "bottle",
    "bus",
    "car",
    "cat",
    "chair",
    "cow",
    "diningtable",
    "dog",
    "horse",
    "motorbike",
    "person",
    "pottedplant",
    "sheep",
    "sofa",
    "train",
    "tvmonitor",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _upload_classification_zip(store, local: Path, blob_prefix: str) -> int:
    """Pack class folders into one ZIP for faster blob upload/import."""
    cls_root = local / "classification"
    if not cls_root.is_dir():
        return 0
    zip_path = local / "classification.zip"
    image_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for cls_dir in sorted(cls_root.iterdir()):
            if not cls_dir.is_dir():
                continue
            for img in sorted(cls_dir.iterdir()):
                if not img.is_file():
                    continue
                arc = f"{cls_dir.name}/{img.name}"
                zf.write(img, arc)
                image_count += 1
    key = f"{blob_prefix.rstrip('/')}/classification.zip"
    _upload_file(store, key, zip_path, "application/zip")
    return image_count


def _upload_file(store, key: str, path: Path, content_type: str | None = None) -> None:
    store.write_bytes(key, path.read_bytes(), content_type)


def _clear_blob_prefix(store, prefix: str) -> int:
    """Delete all blobs under prefix before re-seeding a dataset."""
    p = prefix if prefix.endswith("/") else f"{prefix}/"
    keys = store.list_prefix(p)
    if not keys:
        base = prefix.rstrip("/")
        if store.exists(base):
            store.delete(base)
            print(f"  Cleared 1 existing blob at {base}")
            return 1
        return 0
    for key in keys:
        store.delete(key)
    print(f"  Cleared {len(keys)} existing blob(s) under {prefix}")
    return len(keys)


def _download_reporthook(block_num: int, block_size: int, total_size: int) -> None:
    if total_size <= 0:
        return
    downloaded = min(block_num * block_size, total_size)
    pct = downloaded * 100 // total_size
    mb = downloaded / (1024 * 1024)
    total_mb = total_size / (1024 * 1024)
    print(f"\r    … {mb:.1f}/{total_mb:.1f} MB ({pct}%)", end="", flush=True)


def _download_file_robust(url: str, dest: Path, *, min_bytes: int = 1_000_000) -> None:
    """Download large files with curl retries; fall back to urllib."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size >= min_bytes:
        print(f"  Using cached {dest.name} ({dest.stat().st_size // (1024 * 1024)} MB)")
        return
    curl = shutil.which("curl")
    if curl:
        print(f"  Downloading via curl: {url}")
        result = subprocess.run(
            [curl, "-fL", "--retry", "8", "--retry-delay", "5", "-o", str(dest), url],
            capture_output=True,
            text=True,
            timeout=7200,
        )
        if result.returncode == 0 and dest.is_file() and dest.stat().st_size >= min_bytes:
            print(f"  Downloaded {dest.stat().st_size // (1024 * 1024)} MB")
            return
        if dest.is_file():
            dest.unlink(missing_ok=True)
        if result.stderr:
            print(f"  curl failed: {result.stderr.strip()[:200]}")
    print(f"  Downloading via urllib: {url}")
    urllib.request.urlretrieve(url, dest, reporthook=_download_reporthook)
    print()
    if not dest.is_file() or dest.stat().st_size < min_bytes:
        raise OSError(f"incomplete download for {url}")


def _upload_dir(store, local_dir: Path, blob_prefix: str) -> int:
    count = 0
    for file in local_dir.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(local_dir).as_posix()
        key = f"{blob_prefix.rstrip('/')}/{rel}"
        ctype = None
        if file.suffix.lower() in (".jpg", ".jpeg"):
            ctype = "image/jpeg"
        elif file.suffix.lower() == ".png":
            ctype = "image/png"
        elif file.suffix.lower() == ".csv":
            ctype = "text/csv"
        elif file.suffix.lower() == ".json":
            ctype = "application/json"
        elif file.suffix.lower() == ".zip":
            ctype = "application/zip"
        _upload_file(store, key, file, ctype)
        count += 1
    return count


def _synthetic_jpeg(class_idx: int, sample_idx: int) -> bytes:
    try:
        from PIL import Image

        r = (class_idx * 37 + 40) % 256
        g = (sample_idx * 53 + 60) % 256
        b = (class_idx * 17 + sample_idx * 11) % 256
        img = Image.new("RGB", (160, 160), (r, g, b))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except ImportError:
        # Minimal valid JPEG header fallback
        return b"\xff\xd8\xff\xe0" + os.urandom(512) + b"\xff\xd9"


def _build_classification_folders(root: Path, classes: list[str], per_class: int = 6) -> int:
    total = 0
    for i, cls in enumerate(classes):
        cls_dir = root / "classification" / cls
        cls_dir.mkdir(parents=True, exist_ok=True)
        for j in range(per_class):
            (cls_dir / f"{cls}_{j:03d}.jpg").write_bytes(_synthetic_jpeg(i, j))
            total += 1
    return total


def _build_yolo_zip(path: Path, classes: list[str], image_count: int = 12, single_box: bool = False) -> int:
    """Build YOLO-format ZIP with images/ and labels/."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(image_count):
            img_name = f"images/img_{i:04d}.jpg"
            zf.writestr(img_name, _synthetic_jpeg(i % len(classes), i))
            cls_id = i % len(classes)
            lines = [f"{cls_id} 0.5 0.5 0.4 0.4"]
            if not single_box and i % 3 == 0:
                lines.append(f"{(cls_id + 1) % len(classes)} 0.3 0.3 0.2 0.2")
            elif single_box:
                lines = [f"{cls_id} 0.5 0.5 0.5 0.5"]
            zf.writestr(f"labels/img_{i:04d}.txt", "\n".join(lines))
        zf.writestr("classes.txt", "\n".join(classes))
    return image_count


def _build_multilabel_dataset(root: Path, classes: list[str], image_count: int = 12) -> int:
    img_dir = root / "images"
    manifest_dir = root / "manifest"
    img_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str]] = []
    for i in range(image_count):
        fname = f"img_{i:04d}.jpg"
        (img_dir / fname).write_bytes(_synthetic_jpeg(i % len(classes), i))
        present = classes[i % len(classes)]
        extra = classes[(i + 3) % len(classes)] if i % 2 == 0 else ""
        labels = present if not extra else f"{present};{extra}"
        rows.append((fname, labels))
    manifest_path = manifest_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "labels"])
        writer.writerows(rows)
    return image_count


def _build_regression_dataset(root: Path, image_count: int = 12) -> int:
    img_dir = root / "images"
    targets_dir = root / "targets"
    img_dir.mkdir(parents=True, exist_ok=True)
    targets_dir.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, float]] = []
    for i in range(image_count):
        fname = f"face_{i:04d}.jpg"
        (img_dir / fname).write_bytes(_synthetic_jpeg(i % 10, i))
        age = 18.0 + (i * 3.7) % 62
        rows.append((fname, round(age, 1)))
    targets_path = targets_dir / "targets.csv"
    with targets_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "age"])
        writer.writerows(rows)
    return image_count


def _try_download_imagenette(dest: Path, per_class_limit: int | None = None) -> int | None:
    per_class_limit = _resolve_per_class_limit(per_class_limit)
    try:
        print("  Downloading Imagenette-160 tarball…")
        with tempfile.TemporaryDirectory() as tmp:
            tgz = Path(tmp) / "imagenette.tgz"
            urllib.request.urlretrieve(IMAGENETTE_URL, tgz)
            extract = Path(tmp) / "extract"
            extract.mkdir()
            with tarfile.open(tgz, "r:gz") as tf:
                tf.extractall(extract)
            train_dir = None
            for candidate in extract.rglob("train"):
                if candidate.is_dir():
                    train_dir = candidate
                    break
            if not train_dir:
                return None
            count = 0
            cls_dirs = sorted([d for d in train_dir.iterdir() if d.is_dir()])
            for idx, cls_dir in enumerate(cls_dirs):
                if idx >= len(IMAGENETTE_CLASSES):
                    break
                friendly = IMAGENETTE_CLASSES[idx]
                out_cls = dest / "classification" / friendly
                out_cls.mkdir(parents=True, exist_ok=True)
                taken = 0
                for img in cls_dir.iterdir():
                    if not img.is_file():
                        continue
                    shutil.copy(img, out_cls / img.name)
                    taken += 1
                    count += 1
                    if per_class_limit > 0 and taken >= per_class_limit:
                        break
            return count if count >= 10 else None
    except Exception as exc:
        print(f"  Imagenette download skipped: {exc}")
        return None


def _build_cifar10_classification_zip(zip_path: Path, per_class_limit: int) -> int | None:
    """Pack CIFAR-10 train set directly into classification.zip (no 50k loose files)."""
    try:
        from PIL import Image
    except ImportError:
        print("  CIFAR-10 skipped: Pillow not installed")
        return None
    try:
        print("  Building CIFAR-10 classification.zip from tarball…")
        cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache"))
        cache.mkdir(parents=True, exist_ok=True)
        tgz = cache / "cifar-10-python.tar.gz"
        _download_file_robust(CIFAR10_URL, tgz, min_bytes=50_000_000)
        with tempfile.TemporaryDirectory() as tmp:
            extract = Path(tmp) / "extract"
            extract.mkdir()
            with tarfile.open(tgz, "r:gz") as tf:
                tf.extractall(extract)
            counts = {c: 0 for c in CIFAR10_CLASSES}
            total = 0
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            buf = io.BytesIO()
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for batch_name in (
                    "data_batch_1",
                    "data_batch_2",
                    "data_batch_3",
                    "data_batch_4",
                    "data_batch_5",
                ):
                    batch_files = list(extract.rglob(batch_name))
                    if not batch_files:
                        continue
                    with batch_files[0].open("rb") as f:
                        batch = pickle.load(f, encoding="bytes")
                    for row, label in zip(batch[b"data"], batch[b"labels"]):
                        cls = CIFAR10_CLASSES[int(label)]
                        if per_class_limit > 0 and counts[cls] >= per_class_limit:
                            continue
                        arr = row.reshape(3, 32, 32).transpose(1, 2, 0)
                        buf.seek(0)
                        buf.truncate(0)
                        Image.fromarray(arr).save(buf, format="PNG")
                        arc = f"{cls}/{cls}_{counts[cls]:05d}.png"
                        zf.writestr(arc, buf.getvalue())
                        counts[cls] += 1
                        total += 1
                        if total % 5000 == 0:
                            print(f"    …{total} images packed")
                        if per_class_limit > 0 and all(v >= per_class_limit for v in counts.values()):
                            break
                    if per_class_limit > 0 and all(v >= per_class_limit for v in counts.values()):
                        break
            print(f"    CIFAR-10 zip ready: {total} images")
            return total if total >= 10 else None
    except Exception as exc:
        print(f"  CIFAR-10 zip build skipped: {exc}")
        return None


def _build_imagenette_classification_zip(zip_path: Path, per_class_limit: int) -> int | None:
    try:
        print("  Building Imagenette classification.zip from tarball…")
        cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache"))
        cache.mkdir(parents=True, exist_ok=True)
        tgz = cache / "imagenette2-160.tgz"
        try:
            _download_file_robust(IMAGENETTE_URL, tgz, min_bytes=10_000_000)
        except OSError:
            print("  Imagenette primary URL failed — trying S3 fallback…")
            _download_file_robust(IMAGENETTE_URL_FALLBACK, tgz, min_bytes=10_000_000)
        with tempfile.TemporaryDirectory() as tmp:
            extract = Path(tmp) / "extract"
            extract.mkdir()
            with tarfile.open(tgz, "r:gz") as tf:
                tf.extractall(extract)
            train_dir = next((c for c in extract.rglob("train") if c.is_dir()), None)
            if train_dir is None:
                return None
            count = 0
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, cls_dir in enumerate(sorted(d for d in train_dir.iterdir() if d.is_dir())):
                    if idx >= len(IMAGENETTE_CLASSES):
                        break
                    friendly = IMAGENETTE_CLASSES[idx]
                    taken = 0
                    for img in sorted(cls_dir.iterdir()):
                        if not img.is_file():
                            continue
                        arc = f"{friendly}/{img.name}"
                        zf.write(img, arc)
                        taken += 1
                        count += 1
                        if per_class_limit > 0 and taken >= per_class_limit:
                            break
            print(f"    Imagenette zip ready: {count} images")
            return count if count >= 10 else None
    except Exception as exc:
        print(f"  Imagenette zip build skipped: {exc}")
        return None


def _try_download_cifar10(dest: Path, per_class_limit: int | None = None) -> int | None:
    per_class_limit = _resolve_per_class_limit(per_class_limit)
    try:
        import torchvision

        print("  Downloading CIFAR-10 via torchvision…")
        dataset = torchvision.datasets.CIFAR10(root=str(dest / "_cache"), train=True, download=True)
        counts = {c: 0 for c in CIFAR10_CLASSES}
        total = 0
        for img, label in dataset:
            cls = CIFAR10_CLASSES[label]
            if per_class_limit > 0 and counts[cls] >= per_class_limit:
                continue
            cls_dir = dest / "classification" / cls
            cls_dir.mkdir(parents=True, exist_ok=True)
            img_path = cls_dir / f"{cls}_{counts[cls]:03d}.png"
            img.save(img_path)
            counts[cls] += 1
            total += 1
            if per_class_limit > 0 and all(v >= per_class_limit for v in counts.values()):
                break
        shutil.rmtree(dest / "_cache", ignore_errors=True)
        return total if total >= 10 else None
    except ImportError:
        pass
    except Exception as exc:
        print(f"  CIFAR-10 torchvision skipped: {exc}")

    try:
        print("  Downloading CIFAR-10 tarball (pickle)…")
        with tempfile.TemporaryDirectory() as tmp:
            tgz = Path(tmp) / "cifar.tgz"
            _download_file_robust(CIFAR10_URL, tgz, min_bytes=50_000_000)
            extract = Path(tmp) / "extract"
            extract.mkdir()
            with tarfile.open(tgz, "r:gz") as tf:
                tf.extractall(extract)
            counts = {c: 0 for c in CIFAR10_CLASSES}
            total = 0
            for batch_name in (
                "data_batch_1",
                "data_batch_2",
                "data_batch_3",
                "data_batch_4",
                "data_batch_5",
            ):
                batch_files = list(extract.rglob(f"{batch_name}"))
                if not batch_files:
                    continue
                with batch_files[0].open("rb") as f:
                    batch = pickle.load(f, encoding="bytes")
                data = batch[b"data"]
                labels = batch[b"labels"]
                for row, label in zip(data, labels):
                    cls = CIFAR10_CLASSES[int(label)]
                    if per_class_limit > 0 and counts[cls] >= per_class_limit:
                        continue
                    cls_dir = dest / "classification" / cls
                    cls_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        from PIL import Image

                        arr = row.reshape(3, 32, 32).transpose(1, 2, 0)
                        Image.fromarray(arr).save(cls_dir / f"{cls}_{counts[cls]:03d}.png")
                    except ImportError:
                        (cls_dir / f"{cls}_{counts[cls]:03d}.bin").write_bytes(row.tobytes())
                    counts[cls] += 1
                    total += 1
                    if per_class_limit > 0 and all(v >= per_class_limit for v in counts.values()):
                        break
                if per_class_limit > 0 and all(v >= per_class_limit for v in counts.values()):
                    break
            return total if total >= 10 else None
    except Exception as exc:
        print(f"  CIFAR-10 download skipped: {exc}")
        return None


def _create_efficientnet_checkpoint(
    path: Path,
    *,
    task_type: str,
    num_outputs: int,
    classes: list[str] | None = None,
    target_name: str = "target",
    target_unit: str = "",
) -> None:
    import torch
    import torch.nn as nn
    from torchvision import models

    model = models.efficientnet_b0(weights=None)
    in_features = model.classifier[1].in_features
    if task_type == "regression":
        model.classifier[1] = nn.Linear(in_features, 1)
    elif task_type == "multi_label":
        model.classifier[1] = nn.Linear(in_features, num_outputs)
    else:
        model.classifier[1] = nn.Linear(in_features, num_outputs)

    payload: dict = {
        "model_state_dict": model.state_dict(),
        "classes": classes or [],
        "model_name": "efficientnet_b0",
        "imgsz": 224,
        "task_type": task_type,
        "val_accuracy": 0.85,
    }
    if task_type == "regression":
        payload.update(
            {
                "target_name": target_name,
                "target_unit": target_unit,
                "target_mean": 35.0,
                "target_std": 12.0,
            }
        )
    torch.save(payload, path)


def _try_extract_voc2012(cache_dir: Path) -> Path | None:
    """Download and extract Pascal VOC 2012 trainval once (~2 GB)."""
    marker = cache_dir / ".voc2012_ready"
    voc_root = cache_dir / "VOCdevkit" / "VOC2012"
    if marker.is_file() and voc_root.is_dir():
        return voc_root
    cache_dir.mkdir(parents=True, exist_ok=True)
    tar_path = cache_dir / "VOCtrainval.tar"
    urls = [VOC2012_URL, VOC2012_FALLBACK_URL]
    for url_idx, url in enumerate(urls):
        try:
            if url_idx > 0:
                print("  Trying VOC 2012 fallback URL…")
            else:
                print("  Downloading Pascal VOC 2012 trainval (~2 GB)…")
            if not tar_path.is_file() or tar_path.stat().st_size < 1_000_000_000:
                _download_file_robust(url, tar_path, min_bytes=500_000_000)
            with tarfile.open(tar_path, "r") as tf:
                tf.extractall(cache_dir)
            if voc_root.is_dir():
                marker.write_text("ok", encoding="utf-8")
                return voc_root
        except Exception as exc:
            print(f"  VOC 2012 download failed ({url}): {exc}")
            tar_path.unlink(missing_ok=True)
    return None


def _voc_objects_to_yolo(
    objects: list[ET.Element], img_w: int, img_h: int, *, single_box: bool
) -> list[str]:
    lines: list[str] = []
    for obj in objects:
        name = (obj.findtext("name") or "").strip()
        if name not in VOC_CLASSES:
            continue
        cls_id = VOC_CLASSES.index(name)
        bbox = obj.find("bndbox")
        if bbox is None:
            continue
        xmin = float(bbox.findtext("xmin", "0"))
        ymin = float(bbox.findtext("ymin", "0"))
        xmax = float(bbox.findtext("xmax", "0"))
        ymax = float(bbox.findtext("ymax", "0"))
        bw = max(xmax - xmin, 1.0) / img_w
        bh = max(ymax - ymin, 1.0) / img_h
        cx = (xmin + xmax) / 2.0 / img_w
        cy = (ymin + ymax) / 2.0 / img_h
        lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    if single_box and lines:
        return [lines[0]]
    return lines


def _build_voc_yolo_zip(voc_root: Path, dest_zip: Path, *, single_box: bool = False) -> int:
    jpeg_dir = voc_root / "JPEGImages"
    ann_dir = voc_root / "Annotations"
    written = 0
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as out:
        for xml_file in sorted(ann_dir.glob("*.xml")):
            tree = ET.parse(xml_file)
            root = tree.getroot()
            size = root.find("size")
            if size is None:
                continue
            img_w = int(size.findtext("width", "1"))
            img_h = int(size.findtext("height", "1"))
            objects = root.findall("object")
            if single_box and len(objects) != 1:
                continue
            lines = _voc_objects_to_yolo(objects, img_w, img_h, single_box=single_box)
            if not lines:
                continue
            img_name = root.findtext("filename") or f"{xml_file.stem}.jpg"
            img_path = jpeg_dir / img_name
            if not img_path.is_file():
                img_path = jpeg_dir / f"{xml_file.stem}.jpg"
            if not img_path.is_file():
                continue
            out.writestr(f"images/{img_path.name}", img_path.read_bytes())
            out.writestr(f"labels/{xml_file.stem}.txt", "\n".join(lines))
            written += 1
            if written % 1000 == 0:
                print(f"    …{written} images packed")
        out.writestr("classes.txt", "\n".join(VOC_CLASSES))
    return written


def _build_voc_multilabel(voc_root: Path, root: Path) -> int:
    jpeg_dir = voc_root / "JPEGImages"
    ann_dir = voc_root / "Annotations"
    img_dir = root / "images"
    manifest_dir = root / "manifest"
    img_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str]] = []
    written = 0
    for xml_file in sorted(ann_dir.glob("*.xml")):
        tree = ET.parse(xml_file)
        doc = tree.getroot()
        labels = sorted(
            {
                (obj.findtext("name") or "").strip()
                for obj in doc.findall("object")
                if (obj.findtext("name") or "").strip() in VOC_CLASSES
            }
        )
        if not labels:
            continue
        img_name = doc.findtext("filename") or f"{xml_file.stem}.jpg"
        img_path = jpeg_dir / img_name
        if not img_path.is_file():
            img_path = jpeg_dir / f"{xml_file.stem}.jpg"
        if not img_path.is_file():
            continue
        fname = f"img_{written:05d}.jpg"
        shutil.copy(img_path, img_dir / fname)
        rows.append((fname, ";".join(labels)))
        written += 1
        if written % 1000 == 0:
            print(f"    …{written} images processed")
    manifest_path = manifest_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "labels"])
        writer.writerows(rows)
    return written


def _try_download_coco128_zip(dest_zip: Path, *, single_box: bool = False) -> int | None:
    """Download Ultralytics COCO128 (128 real images, YOLO labels)."""
    try:
        print("  Downloading COCO128 (128 images)…")
        cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache"))
        cached = cache / "coco128.zip"
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "coco128.zip"
            if cached.is_file() and cached.stat().st_size >= 1_000_000:
                print(f"  Using cached {cached.name}")
                shutil.copy2(cached, raw)
            else:
                _download_file_robust(COCO128_URL, raw, min_bytes=1_000_000)
                cache.mkdir(parents=True, exist_ok=True)
                shutil.copy2(raw, cached)
            extract = Path(tmp) / "coco128"
            extract.mkdir()
            with zipfile.ZipFile(raw, "r") as zf:
                zf.extractall(extract)
            # Normalize to images/ + labels/ layout inside dest_zip
            image_files: list[Path] = []
            label_files: dict[str, Path] = {}
            for path in extract.rglob("*.txt"):
                if "label" in str(path).lower():
                    label_files[path.stem] = path
            for path in extract.rglob("*"):
                if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    image_files.append(path)
            if not image_files:
                return None
            with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as out:
                written = 0
                for img_path in sorted(image_files):
                    stem = img_path.stem
                    label_path = label_files.get(stem)
                    if label_path is None:
                        continue
                    label_text = label_path.read_text(encoding="utf-8").strip()
                    if not label_text:
                        continue
                    lines = [ln for ln in label_text.splitlines() if ln.strip()]
                    if single_box:
                        lines = [lines[0]]
                    out.writestr(f"images/{img_path.name}", img_path.read_bytes())
                    out.writestr(f"labels/{stem}.txt", "\n".join(lines))
                    written += 1
                out.writestr("classes.txt", "\n".join(COCO128_CLASSES))
            return written if written >= 10 else None
    except Exception as exc:
        print(f"  COCO128 download skipped: {exc}")
        return None


def _multilabel_from_coco128(root: Path, image_count: int | None = None) -> int:
    """Build multi-label manifest from COCO128 labels."""
    image_count = image_count or min(_seed_image_count(), 128)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "coco128.zip"
            urllib.request.urlretrieve(COCO128_URL, raw)
            extract = Path(tmp) / "coco128"
            extract.mkdir()
            with zipfile.ZipFile(raw, "r") as zf:
                zf.extractall(extract)
            img_dir = root / "images"
            manifest_dir = root / "manifest"
            img_dir.mkdir(parents=True, exist_ok=True)
            manifest_dir.mkdir(parents=True, exist_ok=True)
            rows: list[tuple[str, str]] = []
            written = 0
            for img_path in sorted(extract.rglob("*.jpg")):
                if written >= image_count:
                    break
                stem = img_path.stem
                label_path = next(
                    (p for p in extract.rglob("*.txt") if p.stem == stem and "label" in str(p).lower()),
                    None,
                )
                if label_path is None or not label_path.is_file():
                    continue
                class_ids = set()
                for line in label_path.read_text(encoding="utf-8").splitlines():
                    parts = line.strip().split()
                    if parts:
                        cid = int(float(parts[0]))
                        if 0 <= cid < len(COCO128_CLASSES):
                            class_ids.add(COCO128_CLASSES[cid])
                if not class_ids:
                    continue
                fname = f"img_{written:04d}.jpg"
                shutil.copy(img_path, img_dir / fname)
                rows.append((fname, ";".join(sorted(class_ids))))
                written += 1
            manifest_path = manifest_dir / "manifest.csv"
            with manifest_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["image", "labels"])
                writer.writerows(rows)
            return written
    except Exception as exc:
        print(f"  COCO128 multi-label skipped: {exc}")
        return 0


def _try_download_utkface(root: Path) -> int | None:
    """Download UTKFace-Cropped, parse age from [age]_...jpg filenames."""
    try:
        print("  Downloading UTKFace-Cropped tarball…")
        cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache"))
        cached = cache / "UTKFace.tar.gz"
        with tempfile.TemporaryDirectory() as tmp:
            tgz = Path(tmp) / "UTKFace.tar.gz"
            if cached.is_file() and cached.stat().st_size >= 50_000_000:
                print(f"  Using cached {cached.name} ({cached.stat().st_size // (1024 * 1024)} MB)")
                shutil.copy2(cached, tgz)
            else:
                _download_file_robust(UTKFACE_URL, tgz, min_bytes=50_000_000)
                cache.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tgz, cached)
            extract = Path(tmp) / "extract"
            extract.mkdir()
            with tarfile.open(tgz, "r:gz") as tf:
                tf.extractall(extract)
            img_dir = root / "images"
            targets_dir = root / "targets"
            img_dir.mkdir(parents=True, exist_ok=True)
            targets_dir.mkdir(parents=True, exist_ok=True)
            rows: list[tuple[str, int]] = []
            count = 0
            for src in sorted(extract.rglob("*.jpg")):
                age_str = src.name.split("_", 1)[0]
                if not age_str.isdigit():
                    continue
                age = int(age_str)
                fname = f"face_{count:05d}.jpg"
                shutil.copy(src, img_dir / fname)
                rows.append((fname, age))
                count += 1
                if count % 5000 == 0:
                    print(f"    …{count} images processed")
            if count < 10:
                return None
            targets_path = targets_dir / "targets.csv"
            with targets_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["image", "age"])
                writer.writerows(rows)
            print(f"    UTKFace ready: {count} images")
            return count
    except Exception as exc:
        print(f"  UTKFace download skipped: {exc}")
        return None


def _download_yolo_weights(path: Path) -> None:
    try:
        print("  Downloading YOLOv8n weights…")
        cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache"))
        cached = cache / "yolov8n.pt"
        if cached.is_file() and cached.stat().st_size >= 1_000_000:
            print(f"  Using cached {cached.name}")
            shutil.copy2(cached, path)
            return
        _download_file_robust(YOLO_WEIGHTS_URL, path, min_bytes=1_000_000)
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, cached)
    except Exception as exc:
        print(f"  YOLO download failed ({exc}), writing placeholder bytes")
        path.write_bytes(b"PK" + os.urandom(1024))


def _seed_datasets(store, work: Path, download: bool) -> dict[str, int]:
    counts: dict[str, int] = {}
    specs = {
        "imagenette-160": ("classification", IMAGENETTE_CLASSES),
        "cifar-10": ("classification", CIFAR10_CLASSES),
    }

    for ds_id, (fmt, classes) in specs.items():
        print(f"Dataset: {ds_id}")
        local = work / "datasets" / ds_id
        local.mkdir(parents=True, exist_ok=True)
        prefix = f"marketplace/datasets/{ds_id}/"
        _clear_blob_prefix(store, prefix)
        n = None
        if download:
            if ds_id == "imagenette-160":
                zip_path = local / "classification.zip"
                limit = _resolve_per_class_limit(None)
                n = _build_imagenette_classification_zip(zip_path, limit)
            elif ds_id == "cifar-10":
                zip_path = local / "classification.zip"
                limit = _resolve_per_class_limit(None)
                n = _build_cifar10_classification_zip(zip_path, limit)
        if n is None:
            print(f"  Using synthetic classification folders ({_resolve_per_class_limit(None) or 'full'}/class)")
            n = _build_classification_folders(local, classes, per_class=_resolve_per_class_limit(None) or 20)
            n = _upload_classification_zip(store, local, prefix)
        else:
            key = f"{prefix.rstrip('/')}/classification.zip"
            _upload_file(store, key, local / "classification.zip", "application/zip")
        counts[ds_id] = n
        print(f"  -> {n} images uploaded as classification.zip")

    # Prefer COCO128 for speed/reliability unless SKIP_VOC=0 and VOC is already cached.
    force_coco = os.getenv("SEED_PREFER_COCO128", "1").strip().lower() in ("1", "true", "yes")
    voc_cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache")) / "voc2012"
    voc_root = None
    if download and not force_coco:
        voc_root = _try_extract_voc2012(voc_cache)
    elif download and force_coco:
        print("  Skipping full VOC download (SEED_PREFER_COCO128=1) — using COCO128 for detection tasks")


    # Detection ZIP (full VOC 2012 when available)
    print("Dataset: voc-2012-detection")
    det_local = work / "datasets" / "voc-2012-detection"
    det_local.mkdir(parents=True, exist_ok=True)
    det_zip = det_local / "voc_detection.zip"
    n = None
    if voc_root is not None:
        n = _build_voc_yolo_zip(voc_root, det_zip, single_box=False)
    elif download:
        n = _try_download_coco128_zip(det_zip, single_box=False)
    if n is None:
        n = _build_yolo_zip(det_zip, VOC_CLASSES, image_count=_seed_image_count(), single_box=False)
    det_prefix = "marketplace/datasets/voc-2012-detection/"
    _clear_blob_prefix(store, det_prefix)
    _upload_file(store, f"{det_prefix.rstrip('/')}/voc_detection.zip", det_zip, "application/zip")
    counts["voc-2012-detection"] = n
    print(f"  -> {n} images in ZIP")

    # Localization ZIP
    print("Dataset: voc-single-object")
    loc_local = work / "datasets" / "voc-single-object"
    loc_local.mkdir(parents=True, exist_ok=True)
    loc_zip = loc_local / "voc_localization.zip"
    n = None
    if voc_root is not None:
        n = _build_voc_yolo_zip(voc_root, loc_zip, single_box=True)
    elif download:
        n = _try_download_coco128_zip(loc_zip, single_box=True)
    if n is None:
        n = _build_yolo_zip(loc_zip, VOC_CLASSES, image_count=_seed_image_count(), single_box=True)
    loc_prefix = "marketplace/datasets/voc-single-object/"
    _clear_blob_prefix(store, loc_prefix)
    _upload_file(store, f"{loc_prefix.rstrip('/')}/voc_localization.zip", loc_zip, "application/zip")
    counts["voc-single-object"] = n
    print(f"  -> {n} images in ZIP")

    # Multi-label
    print("Dataset: voc-multilabel")
    ml_local = work / "datasets" / "voc-multilabel"
    ml_local.mkdir(parents=True, exist_ok=True)
    n = None
    if voc_root is not None:
        n = _build_voc_multilabel(voc_root, ml_local)
    elif download:
        n = _multilabel_from_coco128(ml_local)
    if not n:
        n = _build_multilabel_dataset(ml_local, VOC_CLASSES, image_count=_seed_image_count())
    ml_prefix = "marketplace/datasets/voc-multilabel/"
    _clear_blob_prefix(store, ml_prefix)
    _upload_dir(store, ml_local, ml_prefix)
    counts["voc-multilabel"] = n
    print(f"  -> {n} images + manifest")

    # Regression
    print("Dataset: utkface-age")
    reg_local = work / "datasets" / "utkface-age"
    reg_local.mkdir(parents=True, exist_ok=True)
    reg_prefix = "marketplace/datasets/utkface-age/"
    _clear_blob_prefix(store, reg_prefix)
    n = None
    if download:
        n = _try_download_utkface(reg_local)
    if n is None:
        reg_count = _seed_image_count() or 500
        n = _build_regression_dataset(reg_local, image_count=reg_count)
    _upload_dir(store, reg_local, reg_prefix)
    counts["utkface-age"] = n
    print(f"  -> {n} images + targets CSV")

    return counts


def _sync_catalog_image_counts(catalog: dict, counts: dict[str, int]) -> None:
    for ds in catalog.get("datasets", []):
        ds_id = ds.get("id")
        if ds_id in counts:
            ds["image_count"] = counts[ds_id]


def _seed_models(store, work: Path) -> list[str]:
    seeded: list[str] = []
    models_dir = work / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    torch_ok = False
    try:
        import torch  # noqa: F401
        from torchvision import models  # noqa: F401

        torch_ok = True
    except ImportError:
        print("torch/torchvision not installed — EfficientNet checkpoints will use placeholders")

    efficientnet_specs = [
        ("efficientnet-imagenette", "classification", IMAGENETTE_CLASSES, {}),
        ("efficientnet-cifar10", "classification", CIFAR10_CLASSES, {}),
        ("efficientnet-voc-multilabel", "multi_label", VOC_CLASSES, {}),
        (
            "efficientnet-age-regression",
            "regression",
            [],
            {"target_name": "age", "target_unit": "years"},
        ),
    ]

    for model_id, task_type, classes, extra in efficientnet_specs:
        print(f"Model: {model_id}")
        mdir = models_dir / model_id
        mdir.mkdir(parents=True, exist_ok=True)
        weights = mdir / "best.pt"
        if torch_ok:
            num_out = max(len(classes), 1)
            _create_efficientnet_checkpoint(
                weights,
                task_type=task_type,
                num_outputs=num_out if task_type != "regression" else 1,
                classes=classes,
                target_name=extra.get("target_name", "target"),
                target_unit=extra.get("target_unit", ""),
            )
        else:
            weights.write_bytes(b"TORCH_PLACEHOLDER")

        labels: dict = {"classes": classes, "task_type": task_type}
        if task_type == "regression":
            labels = {
                "task_type": "regression",
                "target_name": extra.get("target_name", "age"),
                "target_unit": extra.get("target_unit", "years"),
                "target_mean": 35.0,
                "target_std": 12.0,
            }
        (mdir / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")

        manifest = {
            "task_type": task_type,
            "weights_blob": "best.pt",
            "labels_blob": "labels.json",
            "classes": classes,
            "model_name": "efficientnet_b0",
            "imgsz": 224,
            "metrics": {"accuracy": 0.88} if task_type == "classification" else {"f1_macro": 0.72},
            **extra,
        }
        (mdir / "model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _upload_dir(store, mdir, f"marketplace/models/{model_id}/")
        seeded.append(model_id)
        print(f"  -> uploaded to marketplace/models/{model_id}/")

    for model_id in ("yolov8n-voc-detection", "yolov8n-voc-localization"):
        print(f"Model: {model_id}")
        mdir = models_dir / model_id
        mdir.mkdir(parents=True, exist_ok=True)
        weights = mdir / "best.pt"
        _download_yolo_weights(weights)
        task = "object_detection" if "detection" in model_id else "object_localization"
        manifest = {
            "task_type": task,
            "weights_blob": "best.pt",
            "classes": VOC_CLASSES,
            "model_name": "yolov8n",
            "imgsz": 640,
            "metrics": {"mAP50": 0.6},
        }
        (mdir / "model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _upload_dir(store, mdir, f"marketplace/models/{model_id}/")
        seeded.append(model_id)
        print(f"  -> uploaded to marketplace/models/{model_id}/")

    return seeded


def main() -> None:
    download = os.getenv("SEED_DOWNLOAD", "0").strip() in ("1", "true", "yes")
    store = get_blob_store()
    print(f"Storage backend: {store.backend} (container={store.container})")

    catalog = _load_catalog()
    catalog["updated_at"] = _now()

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        print("\n=== Seeding datasets ===")
        ds_counts = _seed_datasets(store, work, download)
        _sync_catalog_image_counts(catalog, ds_counts)
        print("\n=== Seeding models ===")
        model_ids = _seed_models(store, work)

    CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    store.write_json(CATALOG_KEY, catalog)
    print(f"\nCatalog uploaded to {CATALOG_KEY}")

    print("\n=== Generating dataset previews ===")
    from schemas.marketplace import MarketplaceDatasetItem  # noqa: E402
    from services.marketplace_store import MarketplaceStore  # noqa: E402

    mp_store = MarketplaceStore(store)
    for ds in catalog.get("datasets", []):
        item = MarketplaceDatasetItem.model_validate(ds)
        names = mp_store.ensure_dataset_previews(item)
        print(f"  {item.id}: {len(names)} preview(s)")

    print(f"Datasets seeded: {len(ds_counts)} ({', '.join(ds_counts)})")
    print(f"Models seeded: {len(model_ids)} ({', '.join(model_ids)})")
    print("\nDone. Start the API and open Dataset Library / Model Library in VisionDock.")


if __name__ == "__main__":
    main()
