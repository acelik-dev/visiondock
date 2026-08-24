"""Run on Azure ML compute: multi-label classification with EfficientNet + BCE."""
from __future__ import annotations

import csv
import io
import json
import os
import random
import re
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


def _parse_multilabel_row(row: dict[str, str]) -> tuple[str, list[str]] | None:
    keys = {k.lower(): k for k in row.keys()}
    image_key = keys.get("image") or keys.get("filename") or keys.get("file") or keys.get("path")
    labels_key = keys.get("labels") or keys.get("label") or keys.get("tags")
    if not image_key:
        return None
    image = (row.get(image_key) or "").strip()
    if not image:
        return None
    labels: list[str] = []
    if labels_key:
        raw = (row.get(labels_key) or "").strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    labels = [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        if not labels:
            labels = [p.strip() for p in re.split(r"[;,|]", raw) if p.strip()]
    else:
        for k, v in row.items():
            if k.lower() in ("image", "filename", "file", "path"):
                continue
            val = (v or "").strip().lower()
            if val in ("1", "true", "yes", "y"):
                labels.append(k.strip())
    return image, labels


def _parse_manifest(manifest_data: bytes, manifest_name: str) -> dict[str, list[str]]:
    entries: dict[str, list[str]] = {}
    lower = manifest_name.lower()
    if lower.endswith(".json"):
        payload = json.loads(manifest_data.decode("utf-8", errors="replace"))
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                image = str(item.get("image") or item.get("filename") or "").strip()
                labels_raw = item.get("labels") or item.get("label") or []
                if isinstance(labels_raw, str):
                    labels = [p.strip() for p in re.split(r"[;,|]", labels_raw) if p.strip()]
                elif isinstance(labels_raw, list):
                    labels = [str(x).strip() for x in labels_raw if str(x).strip()]
                else:
                    labels = []
                if image:
                    entries[image.split("/")[-1]] = labels
        elif isinstance(payload, dict):
            for image, labels_raw in payload.items():
                if isinstance(labels_raw, list):
                    entries[str(image).split("/")[-1]] = [str(x).strip() for x in labels_raw]
    else:
        text = manifest_data.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            parsed = _parse_multilabel_row(row)
            if parsed:
                entries[parsed[0].split("/")[-1]] = parsed[1]
    return entries


def _download_multi_label_dataset() -> tuple[Path, list[str], list[tuple[Path, list[str]]]]:
    """Download images + manifest; return local root and sorted label names."""
    prefix = os.environ.get("MULTI_LABEL_PREFIX", "").strip()
    if not prefix:
        key = os.environ.get("DATASET_BLOB_KEY", "")
        if key.endswith("/"):
            prefix = key
        else:
            raise RuntimeError("MULTI_LABEL_PREFIX or DATASET_BLOB_KEY folder prefix is required")
    if not prefix.endswith("/"):
        prefix += "/"

    client, container = _storage_client()
    cc = client.get_container_client(container)
    root = Path("/tmp/visiondock_multi_label")
    if root.exists():
        shutil.rmtree(root)
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    manifest_data: bytes | None = None
    manifest_name = "manifest.csv"

    for blob in cc.list_blobs(name_starts_with=prefix):
        name = blob.name
        rel = name[len(prefix) :]
        if rel.startswith("manifest/"):
            if manifest_data is None:
                manifest_data = cc.download_blob(name).readall()
                manifest_name = rel.split("/")[-1]
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

    if manifest_data is None:
        raise RuntimeError(f"No manifest found under {prefix}manifest/")
    entries = _parse_manifest(manifest_data, manifest_name)
    if not entries:
        raise RuntimeError("Manifest has no labeled rows")

    all_labels: set[str] = set()
    for labels in entries.values():
        all_labels.update(labels)
    label_names = sorted(all_labels)
    if len(label_names) < 1:
        raise RuntimeError("Need at least one label in the manifest")

    index: dict[str, Path] = {}
    for path in images_dir.iterdir():
        if path.is_file():
            index[path.name] = path
            index[_basename_from_stored(path.name)] = path

    pairs: list[tuple[Path, list[str]]] = []
    for image_key, labels in entries.items():
        path = index.get(image_key) or index.get(image_key.split("/")[-1])
        if path is None:
            continue
        pairs.append((path, labels))

    if len(pairs) < 2:
        raise RuntimeError("Need at least 2 matched image/label rows for training")

    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps({"labels": label_names, "rows": len(pairs)}), encoding="utf-8"
    )
    print(f"Matched {len(pairs)} images, {len(label_names)} labels: {label_names}", flush=True)
    return root, label_names, pairs  # type: ignore[return-value]


def _build_splits(
    pairs: list[tuple[Path, list[str]]],
    label_names: list[str],
    val_split: float,
    seed: int,
) -> tuple[list[tuple[Path, list[float]]], list[tuple[Path, list[float]]]]:
    label_to_idx = {name: i for i, name in enumerate(label_names)}

    def _to_vector(labels: list[str]) -> list[float]:
        vec = [0.0] * len(label_names)
        for lbl in labels:
            idx = label_to_idx.get(lbl)
            if idx is not None:
                vec[idx] = 1.0
        return vec

    encoded = [(path, _to_vector(labels)) for path, labels in pairs]
    random.seed(seed)
    random.shuffle(encoded)
    val_count = max(1, int(len(encoded) * val_split))
    val_pairs = encoded[:val_count]
    train_pairs = encoded[val_count:]
    if not train_pairs:
        train_pairs, val_pairs = encoded, encoded[: max(1, len(encoded) // 5)]
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
    label_names: list[str],
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

    labels = {"classes": label_names, "task_type": "multi_label"}
    cc.get_blob_client(f"{prefix}/labels.json").upload_blob(
        json.dumps(labels).encode("utf-8"), overwrite=True
    )

    manifest = {
        "project_id": project_id,
        "job_id": job_name,
        "task_type": "multi_label",
        "weights_blob": f"{prefix}/best.pt",
        "labels_blob": f"{prefix}/labels.json",
        "metrics": metrics,
        "classes": label_names,
    }
    if pipeline:
        manifest["pipeline"] = pipeline
    cc.get_blob_client(f"{prefix}/model.json").upload_blob(
        json.dumps(manifest).encode("utf-8"), overwrite=True
    )
    print(f"VISIONDOCK_MODEL: {json.dumps(manifest)}", flush=True)


def _compute_multilabel_metrics(
    preds: "torch.Tensor", targets: "torch.Tensor", threshold: float = 0.5
) -> dict[str, float]:
    import torch

    pred_bin = (preds >= threshold).float()
    tp = (pred_bin * targets).sum().item()
    fp = (pred_bin * (1 - targets)).sum().item()
    fn = ((1 - pred_bin) * targets).sum().item()
    precision = tp / max(tp + fp, 1e-8)
    recall = tp / max(tp + fn, 1e-8)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)

    # Macro F1 per label
    f1s: list[float] = []
    for i in range(targets.shape[1]):
        p_i = pred_bin[:, i]
        t_i = targets[:, i]
        tp_i = (p_i * t_i).sum().item()
        fp_i = (p_i * (1 - t_i)).sum().item()
        fn_i = ((1 - p_i) * t_i).sum().item()
        prec_i = tp_i / max(tp_i + fp_i, 1e-8)
        rec_i = tp_i / max(tp_i + fn_i, 1e-8)
        f1s.append(2 * prec_i * rec_i / max(prec_i + rec_i, 1e-8))
    macro_f1 = sum(f1s) / max(len(f1s), 1)

    hamming = (pred_bin != targets).float().mean().item()
    subset_acc = (pred_bin == targets).all(dim=1).float().mean().item()

    return {
        "f1": f1,
        "micro_f1": f1,
        "macro_f1": macro_f1,
        "precision": precision,
        "recall": recall,
        "hamming_loss": hamming,
        "subset_accuracy": subset_acc,
    }


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
        mixup_loss,
    )
    from visiondock_preprocess import apply_pil_preprocess, preprocess_config_from_env
    from visiondock_postprocess import load_postprocess_config

    root, label_names, pairs = _download_multi_label_dataset()
    del root

    epochs = int(os.environ.get("EPOCHS", "30"))
    batch = int(os.environ.get("BATCH", "16"))
    imgsz = int(os.environ.get("IMGSZ", "224"))
    lr = float(os.environ.get("LEARNING_RATE", "0.001"))
    val_split = float(os.environ.get("VAL_SPLIT", "0.2"))
    model_name = os.environ.get("MODEL_NAME", "efficientnet_b0")
    device_str = os.environ.get("DEVICE", "0")
    device = torch.device(f"cuda:{device_str}" if torch.cuda.is_available() else "cpu")

    train_pairs, val_pairs = _build_splits(pairs, label_names, val_split, seed=42)
    num_labels = len(label_names)
    print(f"Train: {len(train_pairs)}, Val: {len(val_pairs)}", flush=True)

    normalize = build_normalize_from_env()
    train_tf = build_train_transforms(imgsz, normalize)
    val_tf = build_val_transforms(imgsz, normalize)
    preprocess_cfg = preprocess_config_from_env()
    use_mixup = env_bool("MIXUP_ENABLED")
    use_cutmix = env_bool("CUTMIX_ENABLED")

    class _MultiLabelDataset(Dataset):
        def __init__(self, items: list[tuple[Path, list[float]]], tf):
            self.items = items
            self.tf = tf

        def __len__(self) -> int:
            return len(self.items)

        def __getitem__(self, idx: int):
            path, vec = self.items[idx]
            with Image.open(path) as raw:
                img = apply_pil_preprocess(raw, preprocess_cfg)
            return self.tf(img), torch.tensor(vec, dtype=torch.float32)

    train_loader = DataLoader(
        _MultiLabelDataset(train_pairs, train_tf),
        batch_size=batch,
        shuffle=True,
        num_workers=2,
        pin_memory=torch.cuda.is_available(),
    )
    val_loader = DataLoader(
        _MultiLabelDataset(val_pairs, val_tf),
        batch_size=batch,
        shuffle=False,
        num_workers=2,
        pin_memory=torch.cuda.is_available(),
    )

    if model_name == "efficientnet_b2":
        weights = models.EfficientNet_B2_Weights.IMAGENET1K_V1
        model = models.efficientnet_b2(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_labels)
    else:
        weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1
        model = models.efficientnet_b0(weights=weights)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_labels)

    model = model.to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(epochs, 1))

    best_f1 = 0.0
    best_path = Path("/tmp/best_multi_label.pt")
    last_loss = 0.0
    best_val_metrics: dict[str, float] = {}

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
        all_preds: list[torch.Tensor] = []
        all_targets: list[torch.Tensor] = []
        with torch.no_grad():
            for images, labels in val_loader:
                images = images.to(device)
                logits = model(images)
                probs = torch.sigmoid(logits)
                all_preds.append(probs.cpu())
                all_targets.append(labels)

        val_preds = torch.cat(all_preds, dim=0)
        val_targets = torch.cat(all_targets, dim=0)
        val_metrics = _compute_multilabel_metrics(val_preds, val_targets)

        print(
            f"Epoch {epoch}/{epochs} — loss={last_loss:.4f} "
            f"f1={val_metrics['f1']:.4f} macro_f1={val_metrics['macro_f1']:.4f}",
            flush=True,
        )
        if val_metrics["f1"] >= best_f1:
            best_f1 = val_metrics["f1"]
            best_val_metrics = val_metrics
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "classes": label_names,
                    "model_name": model_name,
                    "imgsz": imgsz,
                    "task_type": "multi_label",
                    "val_f1": val_metrics["f1"],
                    "preprocessing": preprocess_cfg.to_dict(),
                },
                best_path,
            )

    metrics = {
        **best_val_metrics,
        "loss": last_loss,
        "epoch": float(epochs),
        "num_labels": float(num_labels),
    }
    _log_metrics(metrics)

    project_id = os.environ.get("PROJECT_ID", "")
    job_name = os.environ.get("JOB_NAME", "")
    if best_path.exists() and project_id and job_name:
        pipeline = {
            "preprocessing": preprocess_cfg.to_dict(),
            "postprocessing": load_postprocess_config().to_dict(),
        }
        _upload_artifacts(project_id, job_name, best_path, label_names, metrics, pipeline)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Training failed: {exc}", flush=True)
        raise SystemExit(1) from exc
