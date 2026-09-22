"""Focused coverage for finite regression target validation."""

from __future__ import annotations

import unittest

from dataset_validation import MIN_IMAGES, validate_regression_targets


def _validate(targets: list[str]) -> dict:
    rows = [f"image-{i}.jpg,{target}" for i, target in enumerate(targets)]
    data = ("image,target\n" + "\n".join(rows) + "\n").encode("utf-8")
    images = {f"image-{i}.jpg" for i in range(len(targets))}
    return validate_regression_targets(data, images)


class RegressionTargetValidationTests(unittest.TestCase):
    def test_finite_targets_remain_valid(self) -> None:
        for target in ("12.4", "0", "-3.7", "1", "1.25", "1e5"):
            with self.subTest(target=target):
                result = _validate([target] * MIN_IMAGES)
                self.assertTrue(result["valid"], result)
                self.assertEqual(result["errors"], [])
                self.assertEqual(result["warnings"], [])
                self.assertEqual(result["stats"]["target_rows"], MIN_IMAGES)
                self.assertEqual(result["stats"]["target_min"], float(target))
                self.assertEqual(result["stats"]["target_max"], float(target))
                self.assertEqual(result["stats"]["target_mean"], float(target))

    def test_nonfinite_targets_rejected_and_excluded_from_statistics(self) -> None:
        # Keep enough valid matched rows even after rejecting the extra target.
        baseline = [str(i) for i in range(MIN_IMAGES)]
        for target in (
            "NaN", "nan", "+NaN", "-NaN", "Inf", "+Inf", "-Inf",
            "Infinity", "+Infinity", "-Infinity", "iNfInItY", "1e309", "-1e309",
        ):
            with self.subTest(target=target):
                result = _validate([*baseline, target])
                self.assertFalse(result["valid"], result)
                self.assertEqual(
                    result["errors"],
                    [f"Target must be finite for image-{MIN_IMAGES}.jpg"],
                )
                self.assertEqual(result["stats"]["target_rows"], MIN_IMAGES)
                self.assertEqual(result["stats"]["target_min"], 0.0)
                self.assertEqual(result["stats"]["target_max"], float(MIN_IMAGES - 1))
                self.assertEqual(result["stats"]["target_mean"], (MIN_IMAGES - 1) / 2)

    def test_all_nonfinite_targets_have_no_numeric_statistics(self) -> None:
        result = _validate(["NaN"] * MIN_IMAGES)
        self.assertFalse(result["valid"], result)
        self.assertEqual(
            result["errors"],
            [f"Target must be finite for image-{i}.jpg" for i in range(MIN_IMAGES)],
        )
        self.assertEqual(result["stats"]["target_rows"], 0)
        for field in ("target_min", "target_max", "target_mean"):
            self.assertNotIn(field, result["stats"])


if __name__ == "__main__":
    unittest.main()
