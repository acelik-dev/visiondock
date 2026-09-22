"""Lightweight dataset validation (no GPU, minimal cost)."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree

import yaml

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LABEL_HINTS = ("labels", "annotations", "coco", "yolo", "masks", "voc")
YOLO_BBOX_TOLERANCE = 1e-6
# Upload storage prefixes files as "{12-hex}_{original}" — match CSV rows by original name.
_STORED_NAME_PREFIX = re.compile(r"^[0-9a-f]{12}_(.+)$", re.IGNORECASE)


def _original_basename(stored_name: str) -> str:
    """Strip optional upload uuid prefix so CSV rows can use the original filename."""
    base = stored_name.split("/")[-1]
    match = _STORED_NAME_PREFIX.match(base)
    return match.group(1) if match else base


def _upload_name_keys(uploaded_images: set[str]) -> set[str]:
    """Expand stored upload names for matching against CSV/manifest image columns."""
    keys: set[str] = set()
    for img in uploaded_images:
        base = img.split("/")[-1]
        keys.add(img)
        keys.add(base)
        keys.add(_original_basename(base))
    return keys


def _entry_covers_upload(upload_name: str, entry_basenames: set[str]) -> bool:
    base = upload_name.split("/")[-1]
    return base in entry_basenames or _original_basename(base) in entry_basenames or upload_name in entry_basenames


def validate_dataset_zip(data: bytes, expected_classes: list[str] | None = None) -> dict[str, Any]:
    if len(data) < 32:
        return {"valid": False, "errors": ["File is empty or too small"], "stats": {}}

    max_bytes = int(os.getenv("MAX_DATASET_ZIP_BYTES", str(512 * 1024 * 1024)))
    if len(data) > max_bytes:
        return {
            "valid": False,
            "errors": [f"ZIP exceeds limit ({max_bytes // (1024 * 1024)} MB)"],
            "stats": {"size_bytes": len(data)},
        }

    errors: list[str] = []
    warnings: list[str] = []
    image_count = 0
    label_files = 0
    top_dirs: set[str] = set()
    found_class_names: set[str] = set()

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                parts = name.split("/")
                if parts[0]:
                    top_dirs.add(parts[0])
                lower = name.lower()
                ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
                if ext in IMAGE_EXT:
                    image_count += 1
                if any(h in lower for h in LABEL_HINTS) and ext in {".txt", ".json", ".xml", ".csv"}:
                    label_files += 1
                if "/train/" in lower or lower.startswith("train/"):
                    for p in parts:
                        if p in ("train", "val", "test"):
                            continue
                        if p.lower() in {c.lower() for c in (expected_classes or [])}:
                            found_class_names.add(p)
    except zipfile.BadZipFile:
        return {"valid": False, "errors": ["Invalid ZIP archive"], "stats": {}}

    if image_count == 0:
        errors.append("No images found in ZIP (expected jpg/png/webp).")
    if label_files == 0 and image_count > 0:
        warnings.append("No obvious label files detected — folder-only classification layout assumed.")

    if expected_classes:
        missing = [c for c in expected_classes if c.lower() not in {x.lower() for x in found_class_names}]
        if missing and len(found_class_names) > 0:
            warnings.append(f"Expected class folders not found: {', '.join(missing[:5])}")
        elif missing and image_count > 0 and label_files == 0:
            warnings.append(
                f"Could not verify class folders for: {', '.join(missing[:5])}. Manual review recommended."
            )

    valid = len(errors) == 0 and image_count > 0
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "image_count": image_count,
            "label_files": label_files,
            "top_level_entries": sorted(top_dirs)[:20],
            "size_bytes": len(data),
            "detected_class_folders": sorted(found_class_names),
        },
    }


MIN_IMAGES_PER_CLASS = int(os.getenv("MIN_IMAGES_PER_CLASS", "5"))
MIN_CLASSES_WITH_DATA = int(os.getenv("MIN_CLASSES_WITH_DATA", "2"))
MIN_IMAGES = int(os.getenv("MIN_DATASET_IMAGES", "10"))


def validate_classification_dataset(
    expected_classes: list[str] | None,
    class_counts: dict[str, int],
) -> dict[str, Any]:
    """Validate per-class image folders for image recognition training."""
    errors: list[str] = []
    warnings: list[str] = []
    total = sum(class_counts.values())
    populated = {name: count for name, count in class_counts.items() if count > 0}

    if total == 0:
        errors.append("Upload at least one image per class before training.")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "stats": {"image_count": 0, "class_counts": class_counts},
        }

    if len(populated) < MIN_CLASSES_WITH_DATA:
        errors.append(
            f"At least {MIN_CLASSES_WITH_DATA} classes need images "
            f"(currently {len(populated)} with data)."
        )

    low_classes = [name for name, count in class_counts.items() if 0 < count < MIN_IMAGES_PER_CLASS]
    empty_expected = []
    if expected_classes:
        for cls in expected_classes:
            count = class_counts.get(cls, 0)
            if count == 0:
                empty_expected.append(cls)
            elif count < MIN_IMAGES_PER_CLASS:
                low_classes.append(cls)

    if empty_expected:
        warnings.append(
            f"Classes with no images yet: {', '.join(empty_expected[:8])}"
            + ("…" if len(empty_expected) > 8 else "")
        )

    low_unique = sorted(set(low_classes))
    if low_unique:
        warnings.append(
            f"Recommend at least {MIN_IMAGES_PER_CLASS} images per class; "
            f"below minimum: {', '.join(low_unique[:8])}"
            + ("…" if len(low_unique) > 8 else "")
        )

    valid = len(errors) == 0 and all(
        count >= MIN_IMAGES_PER_CLASS for count in populated.values()
    )
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "image_count": total,
            "class_counts": class_counts,
            "classes_with_data": len(populated),
            "min_per_class": MIN_IMAGES_PER_CLASS,
        },
    }


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


def validate_multilabel_manifest(
    manifest_data: bytes,
    manifest_name: str,
    uploaded_images: set[str],
    expected_labels: list[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    entries: dict[str, list[str]] = {}
    label_counts: dict[str, int] = {}

    lower = manifest_name.lower()
    try:
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
                        entries[image] = labels
            elif isinstance(payload, dict):
                for image, labels_raw in payload.items():
                    if isinstance(labels_raw, list):
                        entries[str(image).strip()] = [str(x).strip() for x in labels_raw]
        else:
            text = manifest_data.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                parsed = _parse_multilabel_row(row)
                if parsed:
                    entries[parsed[0]] = parsed[1]
    except Exception as exc:
        return {
            "valid": False,
            "errors": [f"Could not parse manifest: {exc}"],
            "warnings": [],
            "stats": {},
        }

    if not entries:
        errors.append("Manifest is empty or has no recognizable image/labels columns.")

    missing_images: list[str] = []
    empty_labels: list[str] = []
    upload_keys = _upload_name_keys(uploaded_images) if uploaded_images else set()
    for image, labels in entries.items():
        basename = image.split("/")[-1]
        if uploaded_images and basename not in upload_keys and image not in upload_keys:
            missing_images.append(basename)
        if not labels:
            empty_labels.append(basename)
        for lbl in labels:
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

    entry_basenames = {e.split("/")[-1] for e in entries}
    unlabeled_uploads = [
        img for img in uploaded_images if not _entry_covers_upload(img, entry_basenames)
    ]

    if missing_images:
        warnings.append(
            f"Manifest references {len(missing_images)} image(s) not yet uploaded "
            f"(e.g. {', '.join(missing_images[:3])})."
        )
    if unlabeled_uploads:
        examples = [_original_basename(u) for u in unlabeled_uploads[:3]]
        warnings.append(
            f"{len(unlabeled_uploads)} uploaded image(s) missing from manifest "
            f"(e.g. {', '.join(examples)})."
        )
    if empty_labels:
        warnings.append(f"{len(empty_labels)} manifest row(s) have no labels.")

    if expected_labels:
        missing_lbls = [l for l in expected_labels if l not in label_counts]
        if missing_lbls:
            warnings.append(f"Expected labels not in manifest: {', '.join(missing_lbls[:8])}")

    image_count = len(uploaded_images) if uploaded_images else len(entries)
    valid = len(errors) == 0 and len(entries) >= MIN_IMAGES and not empty_labels
    if image_count < MIN_IMAGES:
        errors.append(f"At least {MIN_IMAGES} labeled images required.")

    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "image_count": image_count,
            "manifest_rows": len(entries),
            "label_count": len(label_counts),
            "label_distribution": dict(sorted(label_counts.items(), key=lambda x: -x[1])[:30]),
            "missing_manifest_images": len(missing_images),
            "unlabeled_uploads": len(unlabeled_uploads),
        },
    }


def validate_regression_targets(
    csv_data: bytes,
    uploaded_images: set[str],
    target_name: str = "target",
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    pairs: dict[str, float] = {}

    try:
        text = csv_data.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            errors.append("Target CSV has no header row.")
        else:
            keys = {k.lower(): k for k in reader.fieldnames}
            image_key = keys.get("image") or keys.get("filename") or keys.get("file")
            target_key = keys.get("target") or keys.get(target_name.lower()) or keys.get("value")
            if not image_key or not target_key:
                errors.append("CSV must have image and target columns (image,target).")
            else:
                for row in reader:
                    image = (row.get(image_key) or "").strip()
                    raw_target = (row.get(target_key) or "").strip()
                    if not image or not raw_target:
                        continue
                    try:
                        target = float(raw_target)
                        if not math.isfinite(target):
                            errors.append(f"Target must be finite for {image.split('/')[-1]}")
                            continue
                        pairs[image.split("/")[-1]] = target
                    except ValueError:
                        warnings.append(f"Non-numeric target for {image.split('/')[-1]}")
    except Exception as exc:
        errors.append(f"Could not parse target CSV: {exc}")

    if not pairs and not errors:
        errors.append("No valid image,target rows found.")

    upload_keys = _upload_name_keys(uploaded_images) if uploaded_images else set()
    missing = (
        [img for img in uploaded_images if not _entry_covers_upload(img, set(pairs))]
        if uploaded_images
        else []
    )
    orphan = [img for img in pairs if uploaded_images and img not in upload_keys]

    if missing:
        warnings.append(f"{len(missing)} uploaded image(s) missing targets.")
    if orphan:
        warnings.append(f"{len(orphan)} target row(s) reference images not uploaded.")

    values = list(pairs.values())
    stats: dict[str, Any] = {
        "image_count": len(uploaded_images) if uploaded_images else len(pairs),
        "target_rows": len(pairs),
        "target_name": target_name,
    }
    if values:
        stats["target_min"] = min(values)
        stats["target_max"] = max(values)
        stats["target_mean"] = round(sum(values) / len(values), 4)

    valid = len(errors) == 0 and len(pairs) >= MIN_IMAGES
    if len(pairs) < MIN_IMAGES and not errors:
        errors.append(f"At least {MIN_IMAGES} image,target pairs required.")

    return {"valid": valid, "errors": errors, "warnings": warnings, "stats": stats}


def _detect_annotation_format(names: list[str]) -> str | None:
    lower = [n.lower() for n in names]
    if any(n.endswith("coco.json") or "/annotations.json" in n for n in lower):
        return "coco"
    def _is_yolo_label_path(n: str) -> bool:
        return n.endswith(".txt") and (
            "/labels/" in n
            or n.startswith("labels/")
            or "/label/" in n
            or n.startswith("label/")
        )

    if any(_is_yolo_label_path(n) for n in lower):
        return "yolo"
    if any(n.endswith(".xml") and ("voc" in n or "annotations" in n or "xml" in n) for n in lower):
        return "voc"
    yolo_pairs = sum(1 for n in lower if n.endswith(".txt") and not _is_yolo_label_path(n))
    if yolo_pairs >= 3:
        return "yolo"
    xml_count = sum(1 for n in lower if n.endswith(".xml"))
    if xml_count >= 3:
        return "voc"
    return None


def _zip_path(value: str) -> str:
    normalized = posixpath.normpath(value.replace("\\", "/"))
    return "" if normalized == "." else normalized


def _resolve_yolo_split_path(
    value: Any,
    data_yaml_name: str,
    zip_names: set[str],
    zf: zipfile.ZipFile,
    archive_names: dict[str, str],
) -> set[str] | None:
    values = value if isinstance(value, list) else [value]
    if not values or not all(isinstance(item, str) and item.strip() for item in values):
        return None

    yaml_parent = str(PurePosixPath(data_yaml_name).parent)
    yaml_grandparent = str(PurePosixPath(yaml_parent).parent)
    bases = (yaml_parent, "", yaml_grandparent)
    split_images: set[str] = set()
    for item in values:
        if item.startswith("/"):
            return None
        resolved_images: set[str] | None = None
        for base in bases:
            candidate = _zip_path(posixpath.join(base, item))
            if candidate == ".." or candidate.startswith("../"):
                continue
            prefix = f"{candidate.rstrip('/')}/"
            directory_images = {
                name
                for name in zip_names
                if name.startswith(prefix) and PurePosixPath(name).suffix.lower() in IMAGE_EXT
            }
            if candidate in zip_names and PurePosixPath(candidate).suffix.lower() in IMAGE_EXT:
                resolved_images = {candidate}
                break
            if candidate in zip_names and candidate.lower().endswith(".txt"):
                try:
                    listed_paths = zf.read(archive_names[candidate]).decode("utf-8").splitlines()
                except (KeyError, UnicodeDecodeError):
                    continue
                listed_images: set[str] = set()
                list_parent = str(PurePosixPath(candidate).parent)
                for listed_path in (line.strip() for line in listed_paths if line.strip()):
                    if listed_path.startswith("/"):
                        listed_images = set()
                        break
                    image_candidates = (
                        _zip_path(posixpath.join(list_parent, listed_path)),
                        _zip_path(listed_path),
                    )
                    image_name = next(
                        (
                            name
                            for name in image_candidates
                            if name in zip_names and PurePosixPath(name).suffix.lower() in IMAGE_EXT
                        ),
                        None,
                    )
                    if image_name is None:
                        listed_images = set()
                        break
                    listed_images.add(image_name)
                if listed_images:
                    resolved_images = listed_images
                    break
            if directory_images:
                resolved_images = directory_images
                break
        if resolved_images is None:
            return None
        split_images.update(resolved_images)
    return split_images


def _normalize_yolo_names(raw: Any, errors: list[str]) -> list[str]:
    if isinstance(raw, list):
        names = [str(value).strip() for value in raw]
        if not names or any(not value for value in names):
            errors.append("data.yaml names must contain at least one non-empty class name.")
            return []
        return names

    if isinstance(raw, dict):
        normalized: dict[int, str] = {}
        for raw_id, raw_name in raw.items():
            if isinstance(raw_id, bool):
                errors.append("data.yaml names dictionary keys must be non-negative integer class IDs.")
                return []
            if isinstance(raw_id, int):
                class_id = raw_id
            elif isinstance(raw_id, str) and raw_id.isdigit():
                class_id = int(raw_id)
            else:
                errors.append("data.yaml names dictionary keys must be non-negative integer class IDs.")
                return []
            name = str(raw_name).strip()
            if class_id < 0 or not name or class_id in normalized:
                errors.append("data.yaml names dictionary must use unique non-negative IDs and non-empty names.")
                return []
            normalized[class_id] = name
        expected = list(range(len(normalized)))
        if not normalized or sorted(normalized) != expected:
            errors.append("data.yaml names dictionary IDs must be contiguous starting at 0.")
            return []
        return [normalized[index] for index in expected]

    errors.append("data.yaml must define non-empty names as a list or ID-to-name dictionary.")
    return []


def _image_for_yolo_label(label_name: str, zip_names: set[str]) -> str | None:
    parts = list(PurePosixPath(label_name).parts)
    try:
        label_index = next(i for i, part in enumerate(parts) if part.lower() in ("labels", "label"))
    except StopIteration:
        return None
    parts[label_index] = "images"
    stem = str(PurePosixPath(*parts).with_suffix(""))
    for ext in IMAGE_EXT:
        candidate = f"{stem}{ext}"
        if candidate in zip_names:
            return candidate
    return None


def _validate_yolo_dataset(
    zf: zipfile.ZipFile,
    names: list[str],
) -> tuple[int, int, dict[str, int], list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {}
    archive_names = {_zip_path(name): name for name in names}
    zip_names = set(archive_names)
    yaml_files = [name for name in zip_names if PurePosixPath(name).name == "data.yaml"]
    if not yaml_files:
        if any(PurePosixPath(name).name == "data.yml" for name in zip_names):
            errors.append("Current YOLO trainer requires a file named data.yaml; data.yml is not supported.")
        else:
            errors.append("YOLO dataset must include data.yaml required by the current trainer.")
        return 0, 0, {}, errors, warnings, stats

    data_yaml_name = sorted(yaml_files)[0]
    try:
        config = yaml.safe_load(zf.read(archive_names[data_yaml_name]).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, yaml.YAMLError) as exc:
        errors.append(f"Could not parse {data_yaml_name}: {exc}")
        return 0, 0, {}, errors, warnings, stats
    if not isinstance(config, dict):
        errors.append("data.yaml root must be a mapping/dictionary.")
        return 0, 0, {}, errors, warnings, stats

    train_value = config.get("train")
    validation_key = "val" if "val" in config else "valid"
    validation_value = config.get(validation_key)
    scoped_images: set[str] = set()
    if train_value is None:
        errors.append("data.yaml must define train.")
    else:
        train_images = _resolve_yolo_split_path(
            train_value, data_yaml_name, zip_names, zf, archive_names
        )
        if train_images is None:
            errors.append("data.yaml train path does not resolve inside the ZIP.")
        else:
            scoped_images.update(train_images)
    if validation_value is None:
        errors.append("data.yaml must define val or valid.")
    else:
        validation_images = _resolve_yolo_split_path(
            validation_value, data_yaml_name, zip_names, zf, archive_names
        )
        if validation_images is None:
            errors.append(f"data.yaml {validation_key} path does not resolve inside the ZIP.")
        else:
            scoped_images.update(validation_images)

    class_names = _normalize_yolo_names(config.get("names"), errors)
    class_count = len(class_names)
    if "nc" in config:
        nc = config.get("nc")
        if isinstance(nc, bool) or not isinstance(nc, int) or nc <= 0:
            errors.append("data.yaml nc must be a positive integer when provided.")
        elif class_count and nc != class_count:
            errors.append(f"data.yaml nc ({nc}) must match names count ({class_count}).")

    annotation_count = 0
    labeled_images = 0
    negative_labels = 0
    orphan_labels = 0
    class_counts: dict[str, int] = {}
    label_files = [
        name
        for name in zip_names
        if name.lower().endswith(".txt")
        and any(part.lower() in ("labels", "label") for part in PurePosixPath(name).parts)
    ]
    for label_name in sorted(label_files):
        image_name = _image_for_yolo_label(label_name, zip_names)
        if image_name is None:
            orphan_labels += 1
            warnings.append(f"YOLO label has no matching image: {label_name}")
            continue
        if image_name not in scoped_images:
            continue
        try:
            lines = zf.read(archive_names[label_name]).decode("utf-8").splitlines()
        except (KeyError, UnicodeDecodeError) as exc:
            errors.append(f"Could not read YOLO label {label_name}: {exc}")
            continue
        non_empty = [(line_no, line.strip()) for line_no, line in enumerate(lines, 1) if line.strip()]
        if not non_empty:
            negative_labels += 1
            continue
        if image_name is not None:
            labeled_images += 1
        for line_no, line in non_empty:
            parts = line.split()
            location = f"{label_name}:{line_no}"
            if len(parts) != 5:
                errors.append(f"{location} must contain exactly 5 tokens: class_id x_center y_center width height.")
                continue
            try:
                class_id = int(parts[0])
            except ValueError:
                errors.append(f"{location} class_id must be an integer.")
                continue
            if class_id < 0 or class_id >= class_count:
                errors.append(f"{location} class_id {class_id} is outside the valid range 0..{max(class_count - 1, 0)}.")
                continue
            try:
                x_center, y_center, width, height = (float(value) for value in parts[1:])
            except ValueError:
                errors.append(f"{location} bbox coordinates must be numeric.")
                continue
            coords = (x_center, y_center, width, height)
            if not all(math.isfinite(value) for value in coords):
                errors.append(f"{location} bbox coordinates must be finite numbers.")
                continue
            if not (0.0 <= x_center <= 1.0 and 0.0 <= y_center <= 1.0):
                errors.append(f"{location} x_center and y_center must be between 0 and 1.")
                continue
            if not (0.0 < width <= 1.0 and 0.0 < height <= 1.0):
                errors.append(f"{location} width and height must be greater than 0 and at most 1.")
                continue
            left = x_center - width / 2.0
            right = x_center + width / 2.0
            top = y_center - height / 2.0
            bottom = y_center + height / 2.0
            tolerance = YOLO_BBOX_TOLERANCE
            if left < -tolerance or top < -tolerance or right > 1.0 + tolerance or bottom > 1.0 + tolerance:
                errors.append(f"{location} bbox extends outside normalized image bounds.")
                continue
            if image_name is not None:
                annotation_count += 1
                class_name = class_names[class_id]
                class_counts[class_name] = class_counts.get(class_name, 0) + 1

    if annotation_count == 0 and not errors:
        errors.append("No valid positive YOLO bounding-box annotations found.")
    stats.update(
        {
            "data_yaml": data_yaml_name,
            "negative_label_files": negative_labels,
            "orphan_label_files": orphan_labels,
        }
    )
    return annotation_count, labeled_images, class_counts, errors, warnings, stats


def _parse_yolo_class_names(zf: zipfile.ZipFile, names: list[str]) -> dict[str, str]:
    """Map class id -> name from data.yaml / data.yml / classes.txt when present."""
    id_to_name: dict[str, str] = {}

    for name in names:
        lower = name.lower()
        if not (lower.endswith("classes.txt") or lower.endswith("data.yaml") or lower.endswith("data.yml")):
            continue
        try:
            text = zf.read(name).decode("utf-8", errors="replace")
        except Exception:
            continue

        if lower.endswith("classes.txt"):
            for idx, line in enumerate(text.splitlines()):
                label = line.strip()
                if label and not label.startswith("#"):
                    id_to_name[str(idx)] = label
            if id_to_name:
                return id_to_name
            continue

        # Lightweight YAML parse for common Ultralytics layouts — no PyYAML dependency.
        # names: ['a', 'b']  OR  names:\n  0: a\n  1: b
        list_match = re.search(
            r"(?m)^\s*names\s*:\s*\[([^\]]*)\]",
            text,
        )
        if list_match:
            raw = list_match.group(1)
            parts = [p.strip().strip("'\"") for p in raw.split(",") if p.strip().strip("'\"")]
            for idx, label in enumerate(parts):
                id_to_name[str(idx)] = label
            if id_to_name:
                return id_to_name

        in_names = False
        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r"^names\s*:\s*$", stripped):
                in_names = True
                continue
            if in_names:
                if not stripped or stripped.startswith("#"):
                    continue
                # End of mapping block when indentation returns to top-level key
                if re.match(r"^[A-Za-z_][\w-]*\s*:", stripped) and not re.match(r"^\d+\s*:", stripped):
                    break
                kv = re.match(r"^['\"]?(\d+)['\"]?\s*:\s*['\"]?(.+?)['\"]?\s*$", stripped)
                if kv:
                    id_to_name[kv.group(1)] = kv.group(2).strip().strip("'\"")
                else:
                    break
        if id_to_name:
            return id_to_name

    return id_to_name


def _count_yolo_labels(zf: zipfile.ZipFile, names: list[str]) -> tuple[int, int, dict[str, int]]:
    annotation_count = 0
    labeled_images = 0
    class_counts: dict[str, int] = {}
    id_to_name = _parse_yolo_class_names(zf, names)
    for name in names:
        if not name.lower().endswith(".txt") or name.endswith("/"):
            continue
        if "classes.txt" in name.lower() or "data.yaml" in name.lower() or "data.yml" in name.lower():
            continue
        try:
            lines = zf.read(name).decode("utf-8", errors="replace").strip().splitlines()
        except Exception:
            continue
        if not lines:
            continue
        labeled_images += 1
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 5:
                cls_id = parts[0]
                cls_key = id_to_name.get(cls_id, cls_id)
                class_counts[cls_key] = class_counts.get(cls_key, 0) + 1
                annotation_count += 1
    return annotation_count, labeled_images, class_counts


def _count_coco_labels(zf: zipfile.ZipFile, names: list[str]) -> tuple[int, int, dict[str, int]]:
    coco_files = [n for n in names if n.lower().endswith(".json")]
    for name in coco_files:
        try:
            data = json.loads(zf.read(name).decode("utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(data, dict) or "annotations" not in data:
            continue
        annotations = data.get("annotations") or []
        categories = {c["id"]: c.get("name", str(c["id"])) for c in (data.get("categories") or [])}
        class_counts: dict[str, int] = {}
        for ann in annotations:
            cat = categories.get(ann.get("category_id"), str(ann.get("category_id")))
            class_counts[str(cat)] = class_counts.get(str(cat), 0) + 1
        images = data.get("images") or []
        return len(annotations), len(images), class_counts
    return 0, 0, {}


def _count_voc_labels(zf: zipfile.ZipFile, names: list[str]) -> tuple[int, int, dict[str, int]]:
    xml_files = [n for n in names if n.lower().endswith(".xml")]
    annotation_count = 0
    class_counts: dict[str, int] = {}
    for name in xml_files:
        try:
            root = ElementTree.fromstring(zf.read(name))
        except Exception:
            continue
        objects = root.findall(".//object")
        if not objects:
            continue
        for obj in objects:
            label = (obj.findtext("name") or "unknown").strip()
            class_counts[label] = class_counts.get(label, 0) + 1
            annotation_count += 1
    return annotation_count, len(xml_files), class_counts


def validate_annotated_dataset(
    data: bytes,
    task_type: str = "object_detection",
    expected_classes: list[str] | None = None,
) -> dict[str, Any]:
    """Validate YOLO/COCO/VOC annotated ZIP for detection or localization."""
    if len(data) < 32:
        return {"valid": False, "errors": ["File is empty or too small"], "stats": {}}

    max_bytes = int(os.getenv("MAX_DATASET_ZIP_BYTES", str(512 * 1024 * 1024)))
    if len(data) > max_bytes:
        return {
            "valid": False,
            "errors": [f"ZIP exceeds limit ({max_bytes // (1024 * 1024)} MB)"],
            "stats": {"size_bytes": len(data)},
        }

    errors: list[str] = []
    warnings: list[str] = []
    image_count = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [i.filename for i in zf.infolist() if not i.is_dir()]
            for name in names:
                ext = "." + name.lower().rsplit(".", 1)[-1] if "." in name else ""
                if ext in IMAGE_EXT:
                    image_count += 1

            fmt = _detect_annotation_format(names)
            if not fmt:
                errors.append(
                    "Could not detect annotation format. Expected YOLO (.txt labels), "
                    "COCO (annotations.json), or Pascal VOC (.xml)."
                )
                return {
                    "valid": False,
                    "errors": errors,
                    "warnings": warnings,
                    "stats": {"image_count": image_count, "format": None},
                }

            if fmt == "yolo":
                (
                    ann_count,
                    labeled,
                    class_counts,
                    yolo_errors,
                    yolo_warnings,
                    yolo_stats,
                ) = _validate_yolo_dataset(zf, names)
                errors.extend(yolo_errors)
                warnings.extend(yolo_warnings)
            elif fmt == "coco":
                ann_count, labeled, class_counts = _count_coco_labels(zf, names)
                yolo_stats = {}
            else:
                ann_count, labeled, class_counts = _count_voc_labels(zf, names)
                yolo_stats = {}

            if image_count == 0:
                errors.append("No images found in annotated ZIP.")
            if ann_count == 0:
                errors.append("No bounding-box annotations found.")
            if task_type == "object_localization":
                multi_box = ann_count > labeled and labeled > 0
                if multi_box:
                    warnings.append(
                        "Some images have multiple boxes — object localization expects one object per image."
                    )

            if expected_classes and class_counts:
                found = {str(k).lower() for k in class_counts}
                # YOLO without names file only has numeric ids — skip name check rather than false-warn.
                only_numeric_ids = all(str(k).isdigit() for k in class_counts)
                if not (fmt == "yolo" and only_numeric_ids):
                    missing = [
                        c
                        for c in expected_classes
                        if c.lower() not in found and str(c) not in class_counts
                    ]
                    if missing:
                        warnings.append(
                            f"Expected classes not found in annotations: {', '.join(missing[:8])}"
                        )

            valid = len(errors) == 0 and image_count >= MIN_IMAGES and ann_count > 0
            if image_count < MIN_IMAGES:
                errors.append(f"At least {MIN_IMAGES} images required.")

            return {
                "valid": valid,
                "errors": errors,
                "warnings": warnings,
                "stats": {
                    "image_count": image_count,
                    "annotation_count": ann_count,
                    "labeled_images": labeled,
                    "format": fmt,
                    "class_counts": class_counts,
                    "class_count": len(class_counts),
                    "size_bytes": len(data),
                    **yolo_stats,
                },
            }
    except zipfile.BadZipFile:
        return {"valid": False, "errors": ["Invalid ZIP archive"], "stats": {}}
