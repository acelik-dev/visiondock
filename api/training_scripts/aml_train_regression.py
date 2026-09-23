"""Run on Azure ML compute: image regression with EfficientNet + MSE/MAE."""
from __future__ import annotations

import csv
import io
import json
import math
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


def _basename_from_stored(stored_name: str) -> str:
    parts = stored_name.split("_", 1)
    return parts[1] if len(parts) > 1 else stored_name


def _parse_targets_csv(
    csv_data: bytes, target_name: str
) -> dict[str, float]:
    text = csv_data.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise RuntimeError("Target CSV has no header row")
    keys = {k.lower(): k for k in reader.fieldnames}
    image_key = keys.get("image") or keys.get("filename") or keys.get("file")
    target_key = keys.get(target_name.lower()) or keys.get("target") or keys.get("value")
    if not image_key or not target_key:
        raise RuntimeError("CSV must have image and target columns (image,target)")
    pairs: dict[str, float] = {}
    for row in reader:
        image = (row.get(image_key) or "").strip()
        raw_target = (row.get(target_key) or "").strip()
        if not image or not raw_target:
            continue
        try:
            target = float(raw_target)
            if not math.isfinite(target):
                continue
            pairs[image.split("/")[-1]] = target
        except ValueError:
            continue
    return pairs


def _download_regression_dataset(
    target_name: str,
) -> tuple[list[tuple[Path, float]], float, float]:
    """Download images + targets CSV; return matched pairs and target mean/std."""
    prefix = os.environ.get("REGRESSION_PREFIX", "").strip()
    if not prefix:
        key = os.environ.get("DATASET_BLOB_KEY", "")
        if key.endswith("/"):
            prefix = key
        else:
            raise RuntimeError("REGRESSION_PREFIX or DATASET_BLOB_KEY folder prefix is required")
    if not prefix.endswith("/"):
        prefix += "/"

    client, container = _storage_client()
    cc = client.get_container_client(container)
    root = Path("/tmp/visiondock_regression")
    if root.exists():
        shutil.rmtree(root)
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    targets_data: bytes | None = None

    for blob in cc.list_blobs(name_starts_with=prefix):
        name = blob.name
        rel = name[len(prefix) :]
        if rel.startswith("targets/"):
            if targets_data is None:
                targets_data = cc.download_blob(name).readall()
            continue
        if not rel.startswith("images/"):
            continue
        fname = rel.split("/")[-1]
        if not fname or fname.endswith("/"):
            continue
        ext = "." + fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
        if ext not in image_ext:
            continue
        data = cc.download_blob(name).readall()
        (images_dir / fname).write_bytes(data)

    if targets_data is None:
        raise RuntimeError(f"No targets CSV found under {prefix}targets/")
    target_map = _parse_targets_csv(targets_data, target_name)
    if not target_map:
        raise RuntimeError("Target CSV has no valid rows")

    index: dict[str, Path] = {}
    for path in images_dir.iterdir():
        if path.is_file():
            index[path.name] = path
            index[_basename_from_stored(path.name)] = path

    pairs: list[tuple[Path, float]] = []
    for image_key, target_val in target_map.items():
        path = index.get(image_key) or index.get(image_key.split("/")[-1])
        if path is None:
            continue
        pairs.append((path, target_val))

    if len(pairs) < 2:
        raise RuntimeError("Need at least 2 matched image/target rows for training")

    values = [v for _, v in pairs]
    target_mean = sum(values) / len(values)
    target_std = max(
        (sum((v - target_mean) ** 2 for v in values) / len(values)) ** 0.5,
        1e-6,
    )
    print(
        f"Matched {len(pairs)} images, target mean={target_mean:.4f} std={target_std:.4f}",
        flush=True,
    )
    return pairs, target_mean, target_std


def _build_splits(
    pairs: list[tuple[Path, float]],
    target_mean: float,
    target_std: float,
    val_split: float,
    seed: int,
) -> tuple[list[tuple[Path, float]], list[tuple[Path, float]]]:
    normalized = [(path, (val - target_mean) / target_std) for path, val in pairs]
    random.seed(seed)
    random.shuffle(normalized)
    val_count = max(1, int(len(normalized) * val_split))
    val_pairs = normalized[:val_count]
    train_pairs = normalized[val_count:]
    if not train_pairs:
        train_pairs, val_pairs = normalized, normalized[: max(1, len(normalized) // 5)]
    return train_pairs, val_pairs


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
    target_name: str,
    target_unit: str,
    target_mean: float,
    target_std: float,
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

    labels = {
        "task_type": "regression",
        "target_name": target_name,
        "target_unit": target_unit,
        "target_mean": target_mean,
        "target_std": target_std,
    }
    cc.get_blob_client(f"{prefix}/labels.json").upload_blob(
        json.dumps(labels).encode("utf-8"), overwrite=True
    )

    manifest = {
        "project_id": project_id,
        "job_id": job_name,
        "task_type": "regression",
        "weights_blob": f"{prefix}/best.pt",
        "labels_blob": f"{prefix}/labels.json",
        "metrics": metrics,
        "target_name": target_name,
        "target_unit": target_unit,
        "target_mean": target_mean,
        "target_std": target_std,
    }
    if pipeline:
        manifest["pipeline"] = pipeline
    cc.get_blob_client(f"{prefix}/model.json").upload_blob(
        json.dumps(manifest).encode("utf-8"), overwrite=True
    )
    print(f"VISIONDOCK_MODEL: {json.dumps(manifest)}", flush=True)


def _regression_metrics(
    preds: "torch.Tensor",
    targets: "torch.Tensor",
    target_mean: float,
    target_std: float,
) -> dict[str, float]:
    import torch

    preds_orig = preds * target_std + target_mean
    targets_orig = targets * target_std + target_mean
    mse = torch.mean((preds_orig - targets_orig) ** 2).item()
    mae = torch.mean(torch.abs(preds_orig - targets_orig)).item()
    rmse = mse**0.5
    ss_res = torch.sum((targets_orig - preds_orig) ** 2).item()
    ss_tot = torch.sum((targets_orig - targets_orig.mean()) ** 2).item()
    r2 = 1.0 - ss_res / max(ss_tot, 1e-8)
    return {"mae": mae, "rmse": rmse, "mse": mse, "r2": r2}


def main() -> None:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms
    from PIL import Image

    from visiondock_augment import build_normalize_from_env, build_train_transforms, build_val_transforms, env_bool
    from visiondock_preprocess import apply_pil_preprocess, preprocess_config_from_env
    from visiondock_postprocess import load_postprocess_config

    target_name = os.environ.get("TARGET_NAME", "target")
    target_unit = os.environ.get("TARGET_UNIT", "")

    pairs, target_mean, target_std = _download_regression_dataset(target_name)

    epochs = int(os.environ.get("EPOCHS", "30"))
    batch = int(os.environ.get("BATCH", "16"))
    imgsz = int(os.environ.get("IMGSZ", "224"))
    lr = float(os.environ.get("LEARNING_RATE", "0.001"))
    val_split = float(os.environ.get("VAL_SPLIT", "0.2"))
    model_name = os.environ.get("MODEL_NAME", "efficientnet_b0")
    loss_type = os.environ.get("LOSS_TYPE", "mse").lower()
    device_str = os.environ.get("DEVICE", "0")
    device = torch.device(f"cuda:{device_str}" if torch.cuda.is_available() else "cpu")

    train_pairs, val_pairs = _build_splits(pairs, target_mean, target_std, val_split, seed=42)
    print(f"Train: {len(train_pairs)}, Val: {len(val_pairs)}", flush=True)

    normalize = build_normalize_from_env()
    preprocess_cfg = preprocess_config_from_env()
    if env_bool("AUGMENTATION", True):
        train_tf = build_train_transforms(imgsz, normalize)
    else:
        train_tf = transforms.Compose(
            [
                transforms.Resize((imgsz, imgsz)),
                transforms.ToTensor(),
                normalize,
            ]
        )
    val_tf = build_val_transforms(imgsz, normalize)

    class _RegressionDataset(Dataset):
        def __init__(self, items: list[tuple[Path, float]], tf):
            self.items = items
            self.tf = tf

        def __len__(self) -> int:
            return len(self.items)

        def __getitem__(self, idx: int):
            path, val = self.items[idx]
            with Image.open(path) as raw:
                img = apply_pil_preprocess(raw, preprocess_cfg)
            return self.tf(img), torch.tensor([val], dtype=torch.float32)

    train_loader = DataLoader(
        _RegressionDataset(train_pairs, train_tf),
        batch_size=batch,
        shuffle=True,
        num_workers=2,
        pin_memory=torch.cuda.is_available(),
    )
    val_loader = DataLoader(
        _RegressionDataset(val_pairs, val_tf),
        batch_size=batch,
        shuffle=False,
        num_workers=2,
        pin_memory=torch.cuda.is_available(),
    )

    if model_name == "efficientnet_b2":
        weights = models.EfficientNet_B2_Weights.IMAGENET1K_V1
        model = models.efficientnet_b2(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, 1)
    else:
        weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1
        model = models.efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, 1)

    model = model.to(device)
    criterion = nn.L1Loss() if loss_type == "mae" else nn.MSELoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(epochs, 1))

    best_mae = float("inf")
    best_path = Path("/tmp/best_regression.pt")
    last_loss = 0.0
    best_val_metrics: dict[str, float] = {}

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for images, targets in train_loader:
            images, targets = images.to(device), targets.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)
        scheduler.step()
        last_loss = running_loss / max(len(train_loader.dataset), 1)

        model.eval()
        all_preds: list[torch.Tensor] = []
        all_targets: list[torch.Tensor] = []
        with torch.no_grad():
            for images, targets in val_loader:
                images = images.to(device)
                outputs = model(images)
                all_preds.append(outputs.cpu())
                all_targets.append(targets)

        val_preds = torch.cat(all_preds, dim=0)
        val_targets = torch.cat(all_targets, dim=0)
        val_metrics = _regression_metrics(val_preds, val_targets, target_mean, target_std)

        print(
            f"Epoch {epoch}/{epochs} — loss={last_loss:.4f} "
            f"mae={val_metrics['mae']:.4f} rmse={val_metrics['rmse']:.4f}",
            flush=True,
        )
        if val_metrics["mae"] <= best_mae:
            best_mae = val_metrics["mae"]
            best_val_metrics = val_metrics
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "model_name": model_name,
                    "imgsz": imgsz,
                    "task_type": "regression",
                    "target_name": target_name,
                    "target_unit": target_unit,
                    "target_mean": target_mean,
                    "target_std": target_std,
                    "val_mae": val_metrics["mae"],
                    "preprocessing": preprocess_cfg.to_dict(),
                },
                best_path,
            )

    metrics = {
        **best_val_metrics,
        "loss": last_loss,
        "epoch": float(epochs),
    }
    _log_metrics(metrics)

    project_id = os.environ.get("PROJECT_ID", "")
    job_name = os.environ.get("JOB_NAME", "")
    if best_path.exists() and project_id and job_name:
        pipeline = {
            "preprocessing": preprocess_cfg.to_dict(),
            "postprocessing": load_postprocess_config().to_dict(),
        }
        _upload_artifacts(
            project_id,
            job_name,
            best_path,
            target_name,
            target_unit,
            target_mean,
            target_std,
            metrics,
            pipeline,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Training failed: {exc}", flush=True)
        raise SystemExit(1) from exc
