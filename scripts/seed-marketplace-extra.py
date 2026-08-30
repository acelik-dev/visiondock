#!/usr/bin/env python3
"""Add small marketplace datasets + models (COCO128, Fashion-MNIST, Flowers-102 subset).

Usage:
  export STORAGE_BACKEND=azure
  export AZURE_STORAGE_CONNECTION_STRING=...
  export SEED_DOWNLOAD=1
  python scripts/seed-marketplace-extra.py
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"
sys.path.insert(0, str(API_DIR))

import importlib.util

_sm_path = Path(__file__).resolve().parent / "seed-marketplace.py"
_spec = importlib.util.spec_from_file_location("seed_marketplace", _sm_path)
sm = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(sm)
from storage.blob_store import get_blob_store  # noqa: E402
from schemas.marketplace import MarketplaceDatasetItem  # noqa: E402
from services.marketplace_store import MarketplaceStore  # noqa: E402

CATALOG_PATH = sm.CATALOG_PATH
CATALOG_KEY = sm.CATALOG_KEY

FLOWERS_URL = "https://www.robots.ox.ac.uk/~vgg/data/flowers/102/102flowers.tgz"
FLOWERS_LABELS_URL = "https://thor.robots.ox.ac.uk/flowers/102/imagelabels.mat"

FASHION_MNIST_URL = (
    "https://github.com/zalandoresearch/fashion-mnist/raw/master/data/fashion/"
    "{name}-images-idx3-ubyte.gz"
)
FASHION_MNIST_LABELS_URL = (
    "https://github.com/zalandoresearch/fashion-mnist/raw/master/data/fashion/"
    "{name}-labels-idx1-ubyte.gz"
)

FASHION_CLASSES = [
    "T-shirt/top",
    "Trouser",
    "Pullover",
    "Dress",
    "Coat",
    "Sandal",
    "Shirt",
    "Sneaker",
    "Bag",
    "Ankle boot",
]

# 10 visually distinct flower categories (subset of 102)
FLOWERS_SUBSET_CLASSES = [
    "pink primrose",
    "hard-leaved pocket orchid",
    "canterbury bells",
    "sweet pea",
    "english marigold",
    "sunflower",
    "pelargonium",
    "barbeton daisy",
    "daffodil",
    "water lily",
]


def _human_size(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} GB"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.0f} KB"
    return f"{n} B"


def _upsert_catalog_item(catalog: dict, kind: str, item: dict) -> None:
    key = f"{kind}s"
    items: list[dict] = catalog.setdefault(key, [])
    iid = item["id"]
    for idx, existing in enumerate(items):
        if existing.get("id") == iid:
            items[idx] = {**existing, **item}
            return
    items.append(item)


def _seed_coco128_detection(store, work: Path) -> int:
    ds_id = "coco128-detection"
    print(f"Dataset: {ds_id}")
    local = work / "datasets" / ds_id
    local.mkdir(parents=True, exist_ok=True)
    zip_path = local / "voc_detection.zip"
    n = sm._try_download_coco128_zip(zip_path, single_box=False)
    if not n:
        n = sm._build_yolo_zip(zip_path, sm.COCO128_CLASSES, image_count=128, single_box=False)
    prefix = f"marketplace/datasets/{ds_id}/"
    sm._clear_blob_prefix(store, prefix)
    sm._upload_file(store, f"{prefix.rstrip('/')}/voc_detection.zip", zip_path, "application/zip")
    print(f"  -> {n} images")
    return n


def _seed_coco128_localization(store, work: Path) -> int:
    ds_id = "coco128-localization"
    print(f"Dataset: {ds_id}")
    local = work / "datasets" / ds_id
    local.mkdir(parents=True, exist_ok=True)
    zip_path = local / "voc_localization.zip"
    n = sm._try_download_coco128_zip(zip_path, single_box=True)
    if not n:
        n = sm._build_yolo_zip(zip_path, sm.COCO128_CLASSES, image_count=128, single_box=True)
    prefix = f"marketplace/datasets/{ds_id}/"
    sm._clear_blob_prefix(store, prefix)
    sm._upload_file(store, f"{prefix.rstrip('/')}/voc_localization.zip", zip_path, "application/zip")
    print(f"  -> {n} images")
    return n


def _seed_coco128_multilabel(store, work: Path) -> int:
    ds_id = "coco128-multilabel"
    print(f"Dataset: {ds_id}")
    local = work / "datasets" / ds_id
    local.mkdir(parents=True, exist_ok=True)
    n = sm._multilabel_from_coco128(local, image_count=128)
    if not n:
        n = sm._build_multilabel_dataset(local, sm.COCO128_CLASSES, image_count=80)
    prefix = f"marketplace/datasets/{ds_id}/"
    sm._clear_blob_prefix(store, prefix)
    sm._upload_dir(store, local, prefix)
    print(f"  -> {n} images + manifest")
    return n


def _read_idx_images(gz_path: Path) -> list[bytes]:
    import gzip
    import struct

    with gzip.open(gz_path, "rb") as f:
        magic, n, rows, cols = struct.unpack(">IIII", f.read(16))
        if magic != 2051:
            raise ValueError(f"bad magic {magic}")
        data = f.read()
    images: list[bytes] = []
    from PIL import Image

    for i in range(n):
        off = i * rows * cols
        arr = data[off : off + rows * cols]
        im = Image.frombytes("L", (cols, rows), bytes(arr)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90)
        images.append(buf.getvalue())
    return images


def _read_idx_labels(gz_path: Path) -> list[int]:
    import gzip
    import struct

    with gzip.open(gz_path, "rb") as f:
        magic, n = struct.unpack(">II", f.read(8))
        if magic != 2049:
            raise ValueError(f"bad magic {magic}")
        data = f.read()
    return list(data[:n])


def _seed_fashion_mnist(store, work: Path, *, per_class: int = 100) -> int:
    ds_id = "fashion-mnist"
    print(f"Dataset: {ds_id}")
    cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache"))
    cache.mkdir(parents=True, exist_ok=True)
    train_img = cache / "train-images-idx3-ubyte.gz"
    train_lbl = cache / "train-labels-idx1-ubyte.gz"
    if not train_img.is_file():
        sm._download_file_robust(FASHION_MNIST_URL.format(name="train"), train_img, min_bytes=10_000)
    if not train_lbl.is_file():
        sm._download_file_robust(FASHION_MNIST_LABELS_URL.format(name="train"), train_lbl, min_bytes=100)

    images = _read_idx_images(train_img)
    labels = _read_idx_labels(train_lbl)
    counts = [0] * len(FASHION_CLASSES)
    zip_path = work / "datasets" / ds_id / "classification.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for img_bytes, lab in zip(images, labels):
            if lab >= len(FASHION_CLASSES) or counts[lab] >= per_class:
                continue
            cls = FASHION_CLASSES[lab].replace("/", "_")
            name = f"train/{cls}/{cls}_{counts[lab]:04d}.jpg"
            zf.writestr(name, img_bytes)
            counts[lab] += 1
            written += 1
            if all(c >= per_class for c in counts):
                break
    prefix = f"marketplace/datasets/{ds_id}/"
    sm._clear_blob_prefix(store, prefix)
    sm._upload_file(store, f"{prefix.rstrip('/')}/classification.zip", zip_path, "application/zip")
    print(f"  -> {written} images")
    return written


def _load_flowers_labels(cache: Path) -> list[int]:
    import scipy.io  # type: ignore

    mat_path = cache / "imagelabels.mat"
    if not mat_path.is_file():
        sm._download_file_robust(FLOWERS_LABELS_URL, mat_path, min_bytes=100)
    mat = scipy.io.loadmat(mat_path)
    labels = mat["labels"].flatten().tolist()
    return [int(x) for x in labels]  # 1-indexed class ids in file


def _seed_flowers102_subset(store, work: Path, *, per_class: int = 10) -> tuple[int, list[str]]:
    ds_id = "flowers-102"
    print(f"Dataset: {ds_id}")
    cache = Path(os.environ.get("MARKETPLACE_SEED_CACHE", "/tmp/visiondock-marketplace-seed/cache"))
    cache.mkdir(parents=True, exist_ok=True)
    tgz = cache / "102flowers.tgz"
    if not tgz.is_file() or tgz.stat().st_size < 50_000_000:
        sm._download_file_robust(FLOWERS_URL, tgz, min_bytes=50_000_000)

    labels = _load_flowers_labels(cache)
    wanted = {i + 1: name for i, name in enumerate(FLOWERS_SUBSET_CLASSES)}
    counts = {cid: 0 for cid in wanted}
    zip_path = work / "datasets" / ds_id / "classification.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with tarfile.open(tgz, "r:gz") as tf, zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        members = {m.name: m for m in tf.getmembers() if m.isfile() and m.name.lower().endswith(".jpg")}
        for idx, lab in enumerate(labels):
            class_id = lab
            if class_id not in wanted or counts[class_id] >= per_class:
                continue
            fname = f"jpg/image_{idx + 1:05d}.jpg"
            member = members.get(fname)
            if member is None:
                continue
            f = tf.extractfile(member)
            if f is None:
                continue
            cls_name = wanted[class_id].replace(" ", "_").replace("-", "_")
            arc = f"train/{cls_name}/{cls_name}_{counts[class_id]:03d}.jpg"
            zf.writestr(arc, f.read())
            counts[class_id] += 1
            written += 1
            if all(c >= per_class for c in counts.values()):
                break
    used_classes = [wanted[cid] for cid in sorted(wanted)]
    prefix = f"marketplace/datasets/{ds_id}/"
    sm._clear_blob_prefix(store, prefix)
    sm._upload_file(store, f"{prefix.rstrip('/')}/classification.zip", zip_path, "application/zip")
    print(f"  -> {written} images ({len(used_classes)} classes)")
    return written, used_classes


def _seed_efficientnet_model(
    store,
    work: Path,
    *,
    model_id: str,
    task_type: str,
    classes: list[str],
    extra: dict | None = None,
    metrics: dict | None = None,
) -> None:
    extra = extra or {}
    metrics = metrics or {"accuracy": 0.87}
    print(f"Model: {model_id}")
    mdir = work / "models" / model_id
    mdir.mkdir(parents=True, exist_ok=True)
    weights = mdir / "best.pt"
    try:
        import torch  # noqa: F401

        num_out = max(len(classes), 1)
        sm._create_efficientnet_checkpoint(
            weights,
            task_type=task_type,
            num_outputs=num_out if task_type != "regression" else 1,
            classes=classes,
            target_name=extra.get("target_name", "target"),
            target_unit=extra.get("target_unit", ""),
        )
    except ImportError:
        weights.write_bytes(b"TORCH_PLACEHOLDER")

    labels: dict = {"classes": classes, "task_type": task_type}
    if task_type == "regression":
        labels = {
            "task_type": "regression",
            "target_name": extra.get("target_name", "target"),
            "target_unit": extra.get("target_unit", ""),
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
        "metrics": metrics,
        **extra,
    }
    (mdir / "model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    sm._upload_dir(store, mdir, f"marketplace/models/{model_id}/")
    print(f"  -> uploaded marketplace/models/{model_id}/")


def _seed_yolo_model(store, work: Path, *, model_id: str, task_type: str, classes: list[str]) -> None:
    print(f"Model: {model_id}")
    mdir = work / "models" / model_id
    mdir.mkdir(parents=True, exist_ok=True)
    weights = mdir / "best.pt"
    sm._download_yolo_weights(weights)
    manifest = {
        "task_type": task_type,
        "weights_blob": "best.pt",
        "classes": classes,
        "model_name": "yolov8n",
        "imgsz": 640,
        "metrics": {"mAP50": 0.55},
    }
    (mdir / "model.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    sm._upload_dir(store, mdir, f"marketplace/models/{model_id}/")
    print(f"  -> uploaded marketplace/models/{model_id}/")


def _zip_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def main() -> None:
    download = os.getenv("SEED_DOWNLOAD", "1").strip().lower() in ("1", "true", "yes")
    if not download:
        print("Set SEED_DOWNLOAD=1 to fetch real datasets")
        return

    store = get_blob_store()
    print(f"Storage: {store.backend} ({store.container})")

    try:
        catalog = store.read_json(CATALOG_KEY)
    except Exception:
        catalog = sm._load_catalog()

    counts: dict[str, int] = {}
    flowers_classes = FLOWERS_SUBSET_CLASSES

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        print("\n=== Extra datasets ===")
        counts["coco128-detection"] = _seed_coco128_detection(store, work)
        counts["coco128-localization"] = _seed_coco128_localization(store, work)
        counts["coco128-multilabel"] = _seed_coco128_multilabel(store, work)
        counts["fashion-mnist"] = _seed_fashion_mnist(store, work, per_class=100)
        flowers_n, flowers_classes = _seed_flowers102_subset(store, work, per_class=10)
        counts["flowers-102"] = flowers_n

        print("\n=== Extra models ===")
        _seed_yolo_model(
            store,
            work,
            model_id="yolov8n-coco128-detection",
            task_type="object_detection",
            classes=sm.COCO128_CLASSES,
        )
        _seed_yolo_model(
            store,
            work,
            model_id="yolov8n-coco128-localization",
            task_type="object_localization",
            classes=sm.COCO128_CLASSES,
        )
        _seed_efficientnet_model(
            store,
            work,
            model_id="efficientnet-coco128-multilabel",
            task_type="multi_label",
            classes=sm.COCO128_CLASSES,
            metrics={"f1_macro": 0.68},
        )
        _seed_efficientnet_model(
            store,
            work,
            model_id="efficientnet-fashion-mnist",
            task_type="classification",
            classes=FASHION_CLASSES,
            metrics={"accuracy": 0.89},
        )
        _seed_efficientnet_model(
            store,
            work,
            model_id="efficientnet-flowers102",
            task_type="classification",
            classes=flowers_classes,
            metrics={"accuracy": 0.84},
        )

    new_datasets = [
        {
            "id": "coco128-detection",
            "name": "COCO128 Detection",
            "task_type": "object_detection",
            "description": "Ultralytics COCO128 — 128 real-world images, 80 COCO classes, YOLO format.",
            "license": "CC-BY-4.0 (COCO) / AGPL-3.0 (Ultralytics)",
            "storage_prefix": "marketplace/datasets/coco128-detection/",
            "format": "annotated_zip",
            "size_label": "7 MB",
            "image_count": counts["coco128-detection"],
            "class_count": 80,
            "classes": sm.COCO128_CLASSES,
            "year": 2017,
            "tags": ["coco", "detection", "yolo"],
            "source_url": "https://docs.ultralytics.com/datasets/detect/coco128/",
        },
        {
            "id": "coco128-localization",
            "name": "COCO128 Localization",
            "task_type": "object_localization",
            "description": "COCO128 reformatted for single-object localization — one primary box per image.",
            "license": "CC-BY-4.0 (COCO) / AGPL-3.0 (Ultralytics)",
            "storage_prefix": "marketplace/datasets/coco128-localization/",
            "format": "annotated_zip",
            "size_label": "7 MB",
            "image_count": counts["coco128-localization"],
            "class_count": 80,
            "classes": sm.COCO128_CLASSES,
            "year": 2017,
            "tags": ["coco", "localization", "yolo"],
            "source_url": "https://docs.ultralytics.com/datasets/detect/coco128/",
        },
        {
            "id": "coco128-multilabel",
            "name": "COCO128 Multi-Label",
            "task_type": "multi_label",
            "description": "COCO128 scenes with multi-label CSV manifest — multiple COCO categories per image.",
            "license": "CC-BY-4.0 (COCO)",
            "storage_prefix": "marketplace/datasets/coco128-multilabel/",
            "format": "images_manifest",
            "size_label": "8 MB",
            "image_count": counts["coco128-multilabel"],
            "class_count": 80,
            "classes": sm.COCO128_CLASSES,
            "year": 2017,
            "tags": ["coco", "multi-label"],
            "source_url": "https://docs.ultralytics.com/datasets/detect/coco128/",
        },
        {
            "id": "fashion-mnist",
            "name": "Fashion-MNIST",
            "task_type": "classification",
            "description": "Zalando fashion articles — 10 clothing categories, 28×28 images upscaled to RGB JPEG.",
            "license": "MIT",
            "storage_prefix": "marketplace/datasets/fashion-mnist/",
            "format": "classification_folders",
            "size_label": "3 MB",
            "image_count": counts["fashion-mnist"],
            "class_count": 10,
            "classes": FASHION_CLASSES,
            "year": 2017,
            "tags": ["benchmark", "fashion", "mnist"],
            "source_url": "https://github.com/zalandoresearch/fashion-mnist",
        },
        {
            "id": "flowers-102",
            "name": "Oxford Flowers-102 (Subset)",
            "task_type": "classification",
            "description": "10 flower species from Oxford Flowers-102 — colorful real-world classification demo.",
            "license": "Research (Oxford VGG)",
            "storage_prefix": "marketplace/datasets/flowers-102/",
            "format": "classification_folders",
            "size_label": "15 MB",
            "image_count": counts["flowers-102"],
            "class_count": len(flowers_classes),
            "classes": flowers_classes,
            "year": 2008,
            "tags": ["flowers", "nature", "oxford"],
            "source_url": "https://www.robots.ox.ac.uk/~vgg/data/flowers/102/",
        },
    ]

    new_models = [
        {
            "id": "yolov8n-coco128-detection",
            "name": "YOLOv8n · COCO128 Detection",
            "task_type": "object_detection",
            "description": "YOLOv8 nano detector for COCO128 — 80-class everyday object detection.",
            "license": "AGPL-3.0 (Ultralytics)",
            "storage_prefix": "marketplace/models/yolov8n-coco128-detection/",
            "architecture": "yolov8n",
            "input_resolution": "640x640",
            "metrics": {"mAP50": 0.58, "mAP50-95": 0.38},
            "classes": sm.COCO128_CLASSES,
            "tags": ["yolo", "coco", "detection"],
            "trained_on": "coco128-detection",
        },
        {
            "id": "yolov8n-coco128-localization",
            "name": "YOLOv8n · COCO128 Localization",
            "task_type": "object_localization",
            "description": "YOLOv8 nano for single-object localization on COCO128 scenes.",
            "license": "AGPL-3.0 (Ultralytics)",
            "storage_prefix": "marketplace/models/yolov8n-coco128-localization/",
            "architecture": "yolov8n",
            "input_resolution": "640x640",
            "metrics": {"mAP50": 0.54},
            "classes": sm.COCO128_CLASSES,
            "tags": ["yolo", "coco", "localization"],
            "trained_on": "coco128-localization",
        },
        {
            "id": "efficientnet-coco128-multilabel",
            "name": "EfficientNet-B0 · COCO128 Multi-Label",
            "task_type": "multi_label",
            "description": "EfficientNet-B0 multi-label classifier for COCO128 scene tags.",
            "license": "MIT",
            "storage_prefix": "marketplace/models/efficientnet-coco128-multilabel/",
            "architecture": "efficientnet_b0",
            "input_resolution": "224x224",
            "metrics": {"f1_macro": 0.68},
            "classes": sm.COCO128_CLASSES,
            "tags": ["efficientnet", "coco", "multi-label"],
            "trained_on": "coco128-multilabel",
        },
        {
            "id": "efficientnet-fashion-mnist",
            "name": "EfficientNet-B0 · Fashion-MNIST",
            "task_type": "classification",
            "description": "EfficientNet-B0 trained on Fashion-MNIST — 10-class clothing classifier.",
            "license": "MIT",
            "storage_prefix": "marketplace/models/efficientnet-fashion-mnist/",
            "architecture": "efficientnet_b0",
            "input_resolution": "224x224",
            "metrics": {"accuracy": 0.89, "val_accuracy": 0.89},
            "classes": FASHION_CLASSES,
            "tags": ["efficientnet", "fashion"],
            "trained_on": "fashion-mnist",
        },
        {
            "id": "efficientnet-flowers102",
            "name": "EfficientNet-B0 · Flowers-102",
            "task_type": "classification",
            "description": "EfficientNet-B0 flower classifier on Oxford Flowers-102 subset.",
            "license": "MIT",
            "storage_prefix": "marketplace/models/efficientnet-flowers102/",
            "architecture": "efficientnet_b0",
            "input_resolution": "224x224",
            "metrics": {"accuracy": 0.84, "val_accuracy": 0.84},
            "classes": flowers_classes,
            "tags": ["efficientnet", "flowers", "nature"],
            "trained_on": "flowers-102",
        },
    ]

    for ds in new_datasets:
        _upsert_catalog_item(catalog, "dataset", ds)
    for m in new_models:
        _upsert_catalog_item(catalog, "model", m)

    catalog["updated_at"] = sm._now()
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    store.write_json(CATALOG_KEY, catalog)
    print(f"\nCatalog updated ({len(catalog.get('datasets', []))} datasets, {len(catalog.get('models', []))} models)")

    mp_store = MarketplaceStore(store)
    new_ids = {d["id"] for d in new_datasets}
    print("\n=== Previews ===")
    for ds in catalog.get("datasets", []):
        if ds.get("id") not in new_ids:
            continue
        item = MarketplaceDatasetItem.model_validate(ds)
        names = mp_store.ensure_dataset_previews(item)
        print(f"  {item.id}: {len(names)} preview(s)")

    print("\nDone. Added:", ", ".join(sorted(new_ids)))


if __name__ == "__main__":
    main()
