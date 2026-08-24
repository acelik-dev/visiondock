"""Run on Azure ML compute: download per-class images from blob, train EfficientNet."""
from __future__ import annotations

import json
import os
import random
import shutil
from pathlib import Path

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from azure.storage.blob import BlobServiceClient


def _storage_client() -> tuple[BlobServiceClient, str]:
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or os.environ.get(
        "AZURE_STORAGE_CONNECTION", ""
    )
    container = os.environ.get("AZURE_STORAGE_CONTAINER", "visiondock")
    if not conn:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is required")
    return BlobServiceClient.from_connection_string(conn), container


def _download_classification_dataset() -> Path:
    """Download images under CLASSIFICATION_PREFIX or a classification ZIP blob key."""
    zip_key = os.environ.get("DATASET_BLOB_KEY", "").strip()
    if zip_key.lower().endswith(".zip"):
        return _download_classification_zip(zip_key)

    prefix = os.environ.get("CLASSIFICATION_PREFIX", "").strip()
    if not prefix:
        key = os.environ.get("DATASET_BLOB_KEY", "")
        if key.endswith("/"):
            prefix = key
        else:
            raise RuntimeError("CLASSIFICATION_PREFIX or DATASET_BLOB_KEY folder prefix is required")

    if not prefix.endswith("/"):
        prefix += "/"

    client, container = _storage_client()
    cc = client.get_container_client(container)
    root = Path("/tmp/visiondock_classification")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    count = 0
    for blob in cc.list_blobs(name_starts_with=prefix):
        name = blob.name
        if name.endswith("/"):
            continue
        rel = name[len(prefix) :]
        parts = rel.split("/")
        if len(parts) < 2:
            continue
        class_dir, fname = parts[0], parts[-1]
        ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
        if ext not in image_ext:
            continue
        dest_dir = root / class_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        data = cc.download_blob(name).readall()
        (dest_dir / fname).write_bytes(data)
        count += 1

    if count == 0:
        raise RuntimeError(f"No classification images found under {prefix}")
    print(f"Downloaded {count} images to {root}", flush=True)
    return root


def _download_classification_zip(zip_key: str) -> Path:
    import io
    import zipfile

    client, container = _storage_client()
    cc = client.get_container_client(container)
    raw = cc.download_blob(zip_key).readall()
    if not raw:
        raise RuntimeError(f"Could not download classification ZIP at {zip_key}")

    root = Path("/tmp/visiondock_classification")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    count = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            if name.endswith("/") or name.startswith("__MACOSX"):
                continue
            parts = name.split("/")
            if len(parts) < 2:
                continue
            class_dir, fname = parts[-2], parts[-1]
            ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
            if ext not in image_ext:
                continue
            dest_dir = root / class_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / fname).write_bytes(zf.read(name))
            count += 1

    if count == 0:
        raise RuntimeError(f"No classification images found in ZIP {zip_key}")
    print(f"Extracted {count} images from {zip_key} to {root}", flush=True)
    return root


def _build_splits(data_root: Path, val_split: float, seed: int) -> tuple[list[tuple[Path, int]], list[tuple[Path, int]], list[str]]:
    """Return train/val file lists and class names (sorted)."""
    classes = sorted(d.name for d in data_root.iterdir() if d.is_dir())
    if len(classes) < 2:
        raise RuntimeError("Need at least 2 class folders for classification training")

    class_to_idx = {name: i for i, name in enumerate(classes)}
    pairs: list[tuple[Path, int]] = []
    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for cls in classes:
        cls_dir = data_root / cls
        for path in cls_dir.iterdir():
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext in image_ext:
                pairs.append((path, class_to_idx[cls]))

    random.seed(seed)
    random.shuffle(pairs)
    val_count = max(1, int(len(pairs) * val_split))
    val_pairs = pairs[:val_count]
    train_pairs = pairs[val_count:]
    if not train_pairs:
        train_pairs, val_pairs = pairs, pairs[: max(1, len(pairs) // 5)]
    return train_pairs, val_pairs, classes


def _log_metrics(metrics: dict[str, float]) -> None:
    print(f"VISIONDOCK_METRICS: {json.dumps(metrics)}", flush=True)
    try:
        import mlflow

        for name, value in metrics.items():
            mlflow.log_metric(name, float(value))
    except Exception as exc:
        print(f"mlflow log skipped: {exc}", flush=True)


def _upload_artifacts(
    project_id: str,
    job_name: str,
    weights_path: Path,
    class_names: list[str],
    metrics: dict[str, float],
    pipeline: dict | None = None,
) -> None:
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or os.environ.get(
        "AZURE_STORAGE_CONNECTION", ""
    )
    container = os.environ.get("AZURE_STORAGE_CONTAINER", "visiondock")
    if not conn or not project_id or not job_name:
        print("Artifact upload skipped: missing storage or project/job id", flush=True)
        return

    prefix = f"projects/{project_id}/models/{job_name}"
    client = BlobServiceClient.from_connection_string(conn)
    cc = client.get_container_client(container)
    cc.get_blob_client(f"{prefix}/best.pt").upload_blob(weights_path.read_bytes(), overwrite=True)

    labels = {"classes": class_names}
    cc.get_blob_client(f"{prefix}/labels.json").upload_blob(
        json.dumps(labels).encode("utf-8"), overwrite=True
    )

    manifest = {
        "project_id": project_id,
        "job_id": job_name,
        "task_type": "classification",
        "weights_blob": f"{prefix}/best.pt",
        "labels_blob": f"{prefix}/labels.json",
        "metrics": metrics,
        "classes": class_names,
    }
    if pipeline:
        manifest["pipeline"] = pipeline
    cc.get_blob_client(f"{prefix}/model.json").upload_blob(
        json.dumps(manifest).encode("utf-8"), overwrite=True
    )
    print(f"VISIONDOCK_MODEL: {json.dumps(manifest)}", flush=True)


def main() -> None:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms
    from PIL import Image

    from visiondock_augment import (
        apply_cutmix,
        apply_mixup,
        build_normalize_from_env,
        build_train_transforms,
        build_val_transforms,
        env_bool,
        env_float,
        mixup_loss,
    )
    from visiondock_preprocess import apply_pil_preprocess, preprocess_config_from_env
    from visiondock_postprocess import load_postprocess_config

    data_root = _download_classification_dataset()
    epochs = int(os.environ.get("EPOCHS", "30"))
    batch = int(os.environ.get("BATCH", "16"))
    imgsz = int(os.environ.get("IMGSZ", "224"))
    lr = float(os.environ.get("LEARNING_RATE", "0.001"))
    val_split = float(os.environ.get("VAL_SPLIT", "0.2"))
    model_name = os.environ.get("MODEL_NAME", "efficientnet_b0")
    device_str = os.environ.get("DEVICE", "0")
    device = torch.device(f"cuda:{device_str}" if torch.cuda.is_available() else "cpu")

    train_pairs, val_pairs, class_names = _build_splits(data_root, val_split, seed=42)
    num_classes = len(class_names)
    print(f"Classes ({num_classes}): {class_names}", flush=True)
    print(f"Train: {len(train_pairs)}, Val: {len(val_pairs)}", flush=True)

    normalize = build_normalize_from_env()
    train_tf = build_train_transforms(imgsz, normalize)
    val_tf = build_val_transforms(imgsz, normalize)
    preprocess_cfg = preprocess_config_from_env()
    use_mixup = env_bool("MIXUP_ENABLED")
    use_cutmix = env_bool("CUTMIX_ENABLED")
    label_smoothing = env_float("LABEL_SMOOTHING", 0.0)

    class _PairDataset(Dataset):
        def __init__(self, pairs: list[tuple[Path, int]], tf):
            self.pairs = pairs
            self.tf = tf

        def __len__(self) -> int:
            return len(self.pairs)

        def __getitem__(self, idx: int):
            path, label = self.pairs[idx]
            with Image.open(path) as raw:
                img = apply_pil_preprocess(raw, preprocess_cfg)
            return self.tf(img), label

    train_loader = DataLoader(
        _PairDataset(train_pairs, train_tf),
        batch_size=batch,
        shuffle=True,
        num_workers=2,
        pin_memory=torch.cuda.is_available(),
    )
    val_loader = DataLoader(
        _PairDataset(val_pairs, val_tf),
        batch_size=batch,
        shuffle=False,
        num_workers=2,
        pin_memory=torch.cuda.is_available(),
    )

    if model_name == "efficientnet_b2":
        weights = models.EfficientNet_B2_Weights.IMAGENET1K_V1
        model = models.efficientnet_b2(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)
    else:
        weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1
        model = models.efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)

    model = model.to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=label_smoothing)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(epochs, 1))

    best_acc = 0.0
    best_path = Path("/tmp/best_classification.pt")
    last_loss = 0.0

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            targets_b = None
            lam = 1.0
            if use_cutmix:
                images, labels, targets_b, lam = apply_cutmix(images, labels, alpha=1.0)
            elif use_mixup:
                images, labels, targets_b, lam = apply_mixup(images, labels, alpha=0.2)
            optimizer.zero_grad()
            outputs = model(images)
            loss = mixup_loss(criterion, outputs, labels, targets_b, lam)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)
        scheduler.step()
        last_loss = running_loss / max(len(train_loader.dataset), 1)

        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, preds = torch.max(outputs, 1)
                correct += (preds == labels).sum().item()
                total += labels.size(0)
        val_acc = correct / max(total, 1)

        print(
            f"Epoch {epoch}/{epochs} — loss={last_loss:.4f} val_acc={val_acc:.4f}",
            flush=True,
        )
        if val_acc >= best_acc:
            best_acc = val_acc
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "classes": class_names,
                    "model_name": model_name,
                    "imgsz": imgsz,
                    "val_accuracy": val_acc,
                    "preprocessing": preprocess_cfg.to_dict(),
                },
                best_path,
            )

    metrics = {
        "accuracy": best_acc,
        "val_accuracy": best_acc,
        "loss": last_loss,
        "epoch": float(epochs),
        "num_classes": float(num_classes),
    }
    _log_metrics(metrics)

    project_id = os.environ.get("PROJECT_ID", "")
    job_name = os.environ.get("JOB_NAME", "")
    if best_path.exists() and project_id and job_name:
        pipeline = {
            "preprocessing": preprocess_cfg.to_dict(),
            "postprocessing": load_postprocess_config().to_dict(),
        }
        _upload_artifacts(project_id, job_name, best_path, class_names, metrics, pipeline)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Training failed: {exc}", flush=True)
        raise SystemExit(1) from exc
