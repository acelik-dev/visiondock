"""Focused coverage for finite targets and matched regression samples."""

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
                self.assertEqual(result["stats"]["matched_pairs"], MIN_IMAGES)
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
                self.assertEqual(result["stats"]["matched_pairs"], MIN_IMAGES)
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
        self.assertEqual(result["stats"]["matched_pairs"], 0)
        for field in ("target_min", "target_max", "target_mean"):
            self.assertNotIn(field, result["stats"])


class RegressionMatchedPairTests(unittest.TestCase):
    def test_matched_pair_minimum(self) -> None:
        names = [f"image-{i}.jpg" for i in range(MIN_IMAGES)]
        rows = [(name, str(i)) for i, name in enumerate(names)]
        cases = [
            ("matching", set(names), rows, MIN_IMAGES, True),
            ("orphans only", {"real.jpg"}, rows, 0, False),
            ("too few matching images", set(names[:-1]), rows, MIN_IMAGES - 1, False),
            ("too few targets", set(names), rows[:-1], MIN_IMAGES - 1, False),
            ("extra orphan", set(names), rows + [("ghost.jpg", "42")], MIN_IMAGES, True),
            ("extra targetless image", set(names) | {"extra.jpg"}, rows, MIN_IMAGES, True),
            ("no images", set(), rows, 0, False),
            ("uuid prefixes", {f"abcdef123456_{name}" for name in names}, rows, MIN_IMAGES, True),
            (
                "duplicate upload aliases",
                {f"abcdef123456_{name}" for name in names[:-1]}
                | {f"123456abcdef_{names[0]}"},
                rows, MIN_IMAGES - 1, False,
            ),
        ]
        for label, images, targets, matched, valid in cases:
            with self.subTest(case=label):
                data = ("image,target\n" + "\n".join(f"{name},{value}" for name, value in targets)).encode()
                result = validate_regression_targets(data, images)
                self.assertEqual(result["valid"], valid, result)
                self.assertEqual(result["stats"]["image_count"], len(images))
                self.assertEqual(result["stats"]["target_rows"], len(targets))
                self.assertEqual(result["stats"]["matched_pairs"], matched)
                self.assertEqual(
                    result["errors"],
                    [] if valid else [f"At least {MIN_IMAGES} matched image,target pairs required."],
                )

    def test_nonfinite_matching_target_does_not_meet_minimum(self) -> None:
        for target in ("NaN", "Inf", "-Inf"):
            with self.subTest(target=target):
                result = _validate(["1"] * (MIN_IMAGES - 1) + [target])
                self.assertFalse(result["valid"], result)
                self.assertEqual(result["stats"]["image_count"], MIN_IMAGES)
                self.assertEqual(result["stats"]["target_rows"], MIN_IMAGES - 1)
                self.assertEqual(result["stats"]["matched_pairs"], MIN_IMAGES - 1)
                self.assertEqual(result["errors"], [f"Target must be finite for image-{MIN_IMAGES - 1}.jpg"])

    def test_duplicate_csv_keys_keep_last_finite_value_without_inflating_count(self) -> None:
        rows = [f"image-{i}.jpg,1" for i in range(MIN_IMAGES - 1)]
        rows.extend(["folder/image-0.jpg,7", "image-0.jpg,not-numeric"])
        result = validate_regression_targets(
            ("image,target\n" + "\n".join(rows)).encode(),
            {f"image-{i}.jpg" for i in range(MIN_IMAGES)},
        )
        self.assertFalse(result["valid"], result)
        self.assertEqual(result["stats"]["target_rows"], MIN_IMAGES - 1)
        self.assertEqual(result["stats"]["matched_pairs"], MIN_IMAGES - 1)
        self.assertEqual(result["stats"]["target_max"], 7.0)


class ConfiguredTargetPrecedenceTests(unittest.TestCase):
    def test_column_precedence_and_fallbacks(self) -> None:
        cases = [('score', 'target,score', '1,9', 9), ('score', 'value,score', '2,9', 9), ('score', 'target,value,score', '1,2,9', 9), ('score', 'score', '9', 9), ('score', 'target', '1', 1), ('score', 'value', '2', 2), ('target', 'target,value', '1,2', 1), ('target', 'value', '2', 2), ('Score', 'score', '9', 9), ('', 'value', '2', 2)]
        for target_name, columns, values, expected in cases:
            with self.subTest(target_name=target_name, columns=columns):
                data = (f"filename,{columns}\n" + "".join(f"image-{i}.jpg,{values}\n" for i in range(MIN_IMAGES))).encode()
                images = {f"image-{i}.jpg" for i in range(MIN_IMAGES)}
                result = validate_regression_targets(data, images, target_name)
                self.assertTrue(result["valid"], result)
                self.assertEqual(result["errors"], [])
                self.assertEqual(result["stats"]["matched_pairs"], MIN_IMAGES)
                for key in ("target_min", "target_max", "target_mean"):
                    self.assertEqual(result["stats"][key], float(expected))
                short = validate_regression_targets(data, set(sorted(images)[:-1]), target_name)
                self.assertFalse(short["valid"], short)
                self.assertEqual(short["stats"]["matched_pairs"], MIN_IMAGES - 1)

    def test_selected_nonfinite_value_never_uses_fallback(self) -> None:
        for value in ("NaN", "+Inf", "-Inf"):
            with self.subTest(value=value):
                rows = "".join(f"image-{i}.jpg,1,9\n" for i in range(MIN_IMAGES))
                data = ("filename,target,score\n" + rows + f"bad.jpg,1,{value}\n").encode()
                images = {f"image-{i}.jpg" for i in range(MIN_IMAGES)} | {"bad.jpg"}
                result = validate_regression_targets(data, images, "score")
                self.assertFalse(result["valid"], result)
                self.assertEqual(result["errors"], ["Target must be finite for bad.jpg"])
                self.assertEqual(result["stats"]["target_rows"], MIN_IMAGES)
                self.assertEqual(result["stats"]["matched_pairs"], MIN_IMAGES)
                self.assertEqual(result["stats"]["target_mean"], 9.0)


if __name__ == "__main__":
    unittest.main()
