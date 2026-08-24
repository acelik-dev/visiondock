"""Shared torchvision augmentations + mixup/cutmix for classification training."""
from __future__ import annotations

import os
import random

import numpy as np
import torch
from torchvision import transforms


def env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key) or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return default


def env_float(key: str, default: float = 0.0) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return float(raw)


def build_train_transforms(imgsz: int, normalize: transforms.Normalize) -> transforms.Compose:
    augment = env_bool("AUGMENTATION", True)
    steps: list = [transforms.Resize((imgsz, imgsz))]
    if augment:
        steps.extend(
            [
                transforms.RandomHorizontalFlip(),
                transforms.RandomRotation(15),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05),
                transforms.RandAugment(num_ops=2, magnitude=9),
            ]
        )
    steps.extend([transforms.ToTensor(), normalize])
    return transforms.Compose(steps)


def build_normalize_from_env() -> transforms.Normalize:
    from visiondock_preprocess import preprocess_config_from_env

    cfg = preprocess_config_from_env()
    return transforms.Normalize(mean=list(cfg.normalize_mean), std=list(cfg.normalize_std))


def build_val_transforms(imgsz: int, normalize: transforms.Normalize) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((imgsz, imgsz)),
            transforms.ToTensor(),
            normalize,
        ]
    )


def _rand_bbox(size: int, lam: float) -> tuple[int, int, int, int]:
    cut_ratio = np.sqrt(1.0 - lam)
    cut_w = int(size * cut_ratio)
    cut_h = int(size * cut_ratio)
    cx = random.randint(0, size)
    cy = random.randint(0, size)
    x1 = max(0, cx - cut_w // 2)
    y1 = max(0, cy - cut_h // 2)
    x2 = min(size, x1 + cut_w)
    y2 = min(size, y1 + cut_h)
    return x1, y1, x2, y2


def apply_mixup(
    images: torch.Tensor, targets: torch.Tensor, alpha: float = 0.2
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, float] | tuple[torch.Tensor, torch.Tensor, None, float]:
    if alpha <= 0 or images.size(0) < 2:
        return images, targets, None, 1.0
    lam = float(np.random.beta(alpha, alpha))
    idx = torch.randperm(images.size(0), device=images.device)
    mixed = lam * images + (1.0 - lam) * images[idx]
    return mixed, targets, targets[idx], lam


def apply_cutmix(
    images: torch.Tensor, targets: torch.Tensor, alpha: float = 1.0
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None, float]:
    if alpha <= 0 or images.size(0) < 2:
        return images, targets, None, 1.0
    lam = float(np.random.beta(alpha, alpha))
    idx = torch.randperm(images.size(0), device=images.device)
    b, _, h, w = images.shape
    x1, y1, x2, y2 = _rand_bbox(min(h, w), lam)
    images = images.clone()
    images[:, :, y1:y2, x1:x2] = images[idx, :, y1:y2, x1:x2]
    lam = 1.0 - ((x2 - x1) * (y2 - y1) / max(h * w, 1))
    return images, targets, targets[idx], lam


def mixup_loss(
    criterion,
    outputs: torch.Tensor,
    targets_a: torch.Tensor,
    targets_b: torch.Tensor | None,
    lam: float,
) -> torch.Tensor:
    if targets_b is None:
        return criterion(outputs, targets_a)
    return lam * criterion(outputs, targets_a) + (1.0 - lam) * criterion(outputs, targets_b)
