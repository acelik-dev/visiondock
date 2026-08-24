"""Multi-scale detection ensemble — merge predictions from several input scales."""
from __future__ import annotations

from typing import Any

from tiled_detection import _nms_xyxy


def predict_ensemble(
    model,
    image_array,
    *,
    conf: float,
    iou: float,
    tta: bool,
    scales: tuple[float, ...] = (0.85, 1.0, 1.15),
) -> list[dict[str, Any]]:
    import numpy as np
    from PIL import Image

    img = Image.fromarray(np.asarray(image_array).astype("uint8"))
    w, h = img.size
    names: dict[int, str] = {}
    merged_boxes: list[list[float]] = []
    merged_scores: list[float] = []
    merged_classes: list[int] = []

    for scale in scales:
        nw = max(32, int(w * scale))
        nh = max(32, int(h * scale))
        resized = img.resize((nw, nh), Image.Resampling.BILINEAR)
        arr = np.array(resized)
        sx = w / nw
        sy = h / nh
        results = model.predict(source=arr, conf=conf, iou=iou, augment=tta, verbose=False)
        if not results:
            continue
        names = results[0].names or names
        for box in results[0].boxes or []:
            xyxy = box.xyxy[0].tolist()
            merged_boxes.append(
                [xyxy[0] * sx, xyxy[1] * sy, xyxy[2] * sx, xyxy[3] * sy]
            )
            merged_scores.append(float(box.conf[0]))
            merged_classes.append(int(box.cls[0]))

    if not merged_boxes:
        return []

    keep = _nms_xyxy(merged_boxes, merged_scores, iou)
    detections: list[dict[str, Any]] = []
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
