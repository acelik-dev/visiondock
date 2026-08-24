"""SAHI-style tiled inference: slice large images, detect per tile, merge with NMS."""
from __future__ import annotations

from typing import Any


def _nms_xyxy(
    boxes: list[list[float]],
    scores: list[float],
    iou_threshold: float,
) -> list[int]:
    if not boxes:
        return []
    try:
        import torch
        from torchvision.ops import nms

        boxes_t = torch.tensor(boxes, dtype=torch.float32)
        scores_t = torch.tensor(scores, dtype=torch.float32)
        keep = nms(boxes_t, scores_t, iou_threshold)
        return keep.tolist()
    except Exception:
        # Greedy fallback when torchvision NMS unavailable
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        keep: list[int] = []

        def iou(a: list[float], b: list[float]) -> float:
            x1 = max(a[0], b[0])
            y1 = max(a[1], b[1])
            x2 = min(a[2], b[2])
            y2 = min(a[3], b[3])
            inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
            area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
            union = area_a + area_b - inter
            return inter / union if union > 0 else 0.0

        while order:
            i = order.pop(0)
            keep.append(i)
            order = [j for j in order if iou(boxes[i], boxes[j]) < iou_threshold]
        return keep


def iter_slices(
    width: int,
    height: int,
    slice_size: int,
    overlap_ratio: float,
) -> list[tuple[int, int, int, int]]:
    """Return (x1, y1, x2, y2) windows covering the image."""
    stride = max(1, int(slice_size * (1.0 - overlap_ratio)))
    windows: list[tuple[int, int, int, int]] = []
    if width <= slice_size and height <= slice_size:
        return [(0, 0, width, height)]

    ys = list(range(0, max(height - slice_size + 1, 1), stride))
    xs = list(range(0, max(width - slice_size + 1, 1), stride))
    if not ys or ys[-1] + slice_size < height:
        ys.append(max(0, height - slice_size))
    if not xs or xs[-1] + slice_size < width:
        xs.append(max(0, width - slice_size))

    for y1 in ys:
        for x1 in xs:
            x2 = min(width, x1 + slice_size)
            y2 = min(height, y1 + slice_size)
            windows.append((x1, y1, x2, y2))
    return windows


def predict_tiled(
    model,
    image_array,
    *,
    conf: float,
    iou: float,
    tta: bool,
    slice_size: int = 640,
    overlap_ratio: float = 0.2,
    merge_iou: float | None = None,
) -> list[dict[str, Any]]:
    """Run detection on image tiles and merge results."""
    import numpy as np

    img = np.asarray(image_array)
    h, w = img.shape[:2]
    merge_iou = merge_iou if merge_iou is not None else iou
    names: dict[int, str] = {}
    merged_boxes: list[list[float]] = []
    merged_scores: list[float] = []
    merged_classes: list[int] = []

    for x1, y1, x2, y2 in iter_slices(w, h, slice_size, overlap_ratio):
        crop = img[y1:y2, x1:x2]
        results = model.predict(
            source=crop,
            conf=conf,
            iou=iou,
            augment=tta,
            verbose=False,
        )
        if not results:
            continue
        names = results[0].names or names
        for box in results[0].boxes or []:
            xyxy = box.xyxy[0].tolist()
            merged_boxes.append([xyxy[0] + x1, xyxy[1] + y1, xyxy[2] + x1, xyxy[3] + y1])
            merged_scores.append(float(box.conf[0]))
            merged_classes.append(int(box.cls[0]))

    detections: list[dict[str, Any]] = []
    if not merged_boxes:
        return detections

    keep = _nms_xyxy(merged_boxes, merged_scores, merge_iou)
    for idx in keep:
        cls_id = merged_classes[idx]
        detections.append(
            {
                "class_id": cls_id,
                "class_name": names.get(cls_id, str(cls_id)),
                "confidence": merged_scores[idx],
                "bbox_xyxy": merged_boxes[idx],
            }
        )
    return detections
