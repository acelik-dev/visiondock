"""Focused preflight tests for annotated YOLO bbox datasets."""

from __future__ import annotations

import io
import unittest
import zipfile

from dataset_validation import validate_annotated_dataset


def _dataset(
    *,
    data_yaml: str | None = "train: images/train\nval: images/val\nnames: [cat, dog]\n",
    yaml_name: str = "data.yaml",
    prefix: str = "",
    train_label: str | None = "0 0.5 0.5 0.2 0.2\n",
    val_label: str | None = "1 0.5 0.5 0.2 0.2\n",
    extra: dict[str, str | bytes] | None = None,
) -> bytes:
    root = f"{prefix.rstrip('/')}/" if prefix else ""
    entries: dict[str, str | bytes] = {}
    if data_yaml is not None:
        entries[f"{root}{yaml_name}"] = data_yaml
    for index in range(5):
        entries[f"{root}images/train/train-{index}.jpg"] = b"image"
        if train_label is not None:
            entries[f"{root}labels/train/train-{index}.txt"] = train_label
        entries[f"{root}images/val/val-{index}.jpg"] = b"image"
        if val_label is not None:
            entries[f"{root}labels/val/val-{index}.txt"] = val_label
    for name, value in (extra or {}).items():
        entries[f"{root}{name}"] = value
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, value in entries.items():
            zf.writestr(name, value)
    return payload.getvalue()


def _validate(**kwargs):
    return validate_annotated_dataset(_dataset(**kwargs), "object_detection", ["cat", "dog"])


class YoloDatasetValidationTests(unittest.TestCase):
    def assertInvalid(self, result: dict, message: str) -> None:  # noqa: N802
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(message.lower() in error.lower() for error in result["errors"]), result)

    def test_valid_minimal_names_list_and_nc_omitted(self) -> None:
        result = _validate()
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["stats"]["annotation_count"], 10)

    def test_nested_layout_and_names_dictionary(self) -> None:
        result = _validate(
            prefix="export/dataset",
            data_yaml="train: images/train\nval: images/val\nnames:\n  0: cat\n  1: dog\nnc: 2\n",
        )
        self.assertTrue(result["valid"], result)

    def test_valid_alias_is_accepted(self) -> None:
        result = _validate(data_yaml="train: images/train\nvalid: images/val\nnames: [cat, dog]\n")
        self.assertTrue(result["valid"], result)

    def test_null_val_does_not_fall_back_to_valid(self) -> None:
        result = _validate(
            data_yaml="train: images/train\nval: null\nvalid: images/val\nnames: [cat, dog]\n"
        )
        self.assertInvalid(result, "define val or valid")

    def test_missing_or_wrong_yaml_name(self) -> None:
        self.assertInvalid(_validate(data_yaml=None), "data.yaml")
        self.assertInvalid(_validate(yaml_name="data.yml"), "requires a file named data.yaml")

    def test_malformed_or_non_mapping_yaml(self) -> None:
        self.assertInvalid(_validate(data_yaml="names: [cat\n"), "could not parse")
        self.assertInvalid(_validate(data_yaml="- cat\n- dog\n"), "mapping")

    def test_required_split_fields_and_resolution(self) -> None:
        cases = (
            ("val: images/val\nnames: [cat, dog]\n", "define train"),
            ("train: images/train\nnames: [cat, dog]\n", "define val or valid"),
            ("train: images/missing\nval: images/val\nnames: [cat, dog]\n", "train path"),
            ("train: images/train\nval: images/missing\nnames: [cat, dog]\n", "val path"),
        )
        for config, message in cases:
            with self.subTest(message=message):
                self.assertInvalid(_validate(data_yaml=config), message)

    def test_names_and_nc_contract(self) -> None:
        cases = (
            ("train: images/train\nval: images/val\n", "must define non-empty names"),
            ("train: images/train\nval: images/val\nnames: []\n", "at least one non-empty"),
            ("train: images/train\nval: images/val\nnames: {0: cat, 2: dog}\n", "contiguous"),
            ("train: images/train\nval: images/val\nnames: {-1: cat, 0: dog}\n", "unique non-negative"),
            ("train: images/train\nval: images/val\nnames: {false: cat, 1: dog}\n", "integer class IDs"),
            ("train: images/train\nval: images/val\nnames: {0.0: cat, 1: dog}\n", "integer class IDs"),
            ("train: images/train\nval: images/val\nnames: [cat, dog]\nnc: 0\n", "positive integer"),
            ("train: images/train\nval: images/val\nnames: [cat, dog]\nnc: two\n", "positive integer"),
            ("train: images/train\nval: images/val\nnames: [cat, dog]\nnc: 3\n", "must match"),
        )
        for config, message in cases:
            with self.subTest(message=message):
                self.assertInvalid(_validate(data_yaml=config), message)

    def test_invalid_annotation_rows(self) -> None:
        cases = (
            ("0 0.5 0.5 0.2\n", "exactly 5 tokens"),
            ("0 0.5 0.5 0.2 0.2 extra\n", "exactly 5 tokens"),
            ("cat 0.5 0.5 0.2 0.2\n", "class_id must be an integer"),
            ("-1 0.5 0.5 0.2 0.2\n", "outside the valid range"),
            ("2 0.5 0.5 0.2 0.2\n", "outside the valid range"),
            ("0 nope 0.5 0.2 0.2\n", "must be numeric"),
            ("0 nan 0.5 0.2 0.2\n", "finite"),
            ("0 inf 0.5 0.2 0.2\n", "finite"),
            ("0 1.1 0.5 0.2 0.2\n", "between 0 and 1"),
            ("0 0.5 0.5 0 0.2\n", "greater than 0"),
            ("0 0.5 0.5 -0.1 0.2\n", "greater than 0"),
            ("0 0.5 0.5 1.1 0.2\n", "at most 1"),
            ("0 0.05 0.5 0.2 0.2\n", "outside normalized image bounds"),
        )
        for row, message in cases:
            with self.subTest(row=row):
                self.assertInvalid(_validate(train_label=row), message)

    def test_small_boundary_rounding_tolerance(self) -> None:
        row = "0 0.0999995 0.5 0.2 0.2\n"
        result = _validate(train_label=row)
        self.assertTrue(result["valid"], result)

    def test_empty_and_missing_labels_are_valid_negatives(self) -> None:
        self.assertTrue(_validate(train_label="")["valid"])
        self.assertTrue(_validate(train_label=None)["valid"])

    def test_negatives_plus_one_positive_are_accepted(self) -> None:
        result = _validate(
            train_label="",
            val_label="",
            extra={"labels/train/train-0.txt": "0 0.5 0.5 0.2 0.2\n"},
        )
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["stats"]["annotation_count"], 1)

    def test_no_positive_bbox_is_rejected(self) -> None:
        self.assertInvalid(_validate(train_label="", val_label=""), "no valid positive")

    def test_orphan_label_is_warning_not_error(self) -> None:
        result = _validate(extra={"labels/train/orphan.txt": "0 0.5 0.5 0.2 0.2\n"})
        self.assertTrue(result["valid"], result)
        self.assertTrue(any("no matching image" in warning for warning in result["warnings"]), result)

    def test_orphan_label_does_not_supply_required_positive_bbox(self) -> None:
        result = _validate(
            train_label="",
            val_label="",
            extra={"labels/train/orphan.txt": "0 0.5 0.5 0.2 0.2\n"},
        )
        self.assertInvalid(result, "no valid positive")
        self.assertTrue(any("no matching image" in warning for warning in result["warnings"]), result)

    def test_positive_bbox_outside_configured_splits_does_not_count(self) -> None:
        result = _validate(
            train_label="",
            val_label="",
            extra={
                "images/test/test.jpg": b"image",
                "labels/test/test.txt": "0 0.5 0.5 0.2 0.2\n",
            },
        )
        self.assertInvalid(result, "no valid positive")

    def test_malformed_label_outside_configured_splits_is_ignored(self) -> None:
        result = _validate(
            extra={
                "images/test/test.jpg": b"image",
                "labels/test/test.txt": "malformed annotation\n",
            }
        )
        self.assertTrue(result["valid"], result)


if __name__ == "__main__":
    unittest.main()
