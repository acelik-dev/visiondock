"""Offline coverage of the actual regression trainer CSV parser."""
from __future__ import annotations

from pathlib import Path
import runpy
import types
import unittest
from unittest.mock import patch


def _load_parser():
    # The parser needs no Azure services; stub only the module-level SDK import.
    modules = {
        name: types.ModuleType(name)
        for name in ("azure", "azure.storage", "azure.storage.blob")
    }
    modules["azure.storage.blob"].BlobServiceClient = object
    with patch.dict("sys.modules", modules):
        namespace = runpy.run_path(
            str(Path(__file__).parent / "training_scripts" / "aml_train_regression.py")
        )
    return namespace["_parse_targets_csv"]


_parse_targets_csv = _load_parser()


class RegressionTrainerTargetTests(unittest.TestCase):
    def test_finite_targets_preserved(self) -> None:
        for raw in ("12.4", "0", "-3.7", "1e5"):
            with self.subTest(target=raw):
                self.assertEqual(
                    _parse_targets_csv(f"image,target\na.jpg,{raw}\n".encode(), "target"),
                    {"a.jpg": float(raw)},
                )

    def test_nonfinite_targets_skipped_in_mixed_input(self) -> None:
        for raw in (
            "NaN", "nan", "+NaN", "-NaN", "Inf", "+Inf", "-Inf",
            "Infinity", "+Infinity", "-Infinity", "iNfInItY", "1e309", "-1e309",
        ):
            with self.subTest(target=raw):
                data = (
                    f"image,target\na.jpg,12.4\nb.jpg,{raw}\n"
                    "c.jpg,0\nd.jpg,-3.7\ne.jpg,1e5\n"
                ).encode()
                self.assertEqual(
                    _parse_targets_csv(data, "target"),
                    {"a.jpg": 12.4, "c.jpg": 0.0, "d.jpg": -3.7, "e.jpg": 1e5},
                )

    def test_all_nonfinite_targets_return_empty_mapping(self) -> None:
        self.assertEqual(
            _parse_targets_csv(b"image,target\na.jpg,NaN\nb.jpg,Inf\nc.jpg,-Inf\n", "target"),
            {},
        )

    def test_nonfinite_duplicate_does_not_replace_finite_target(self) -> None:
        self.assertEqual(
            _parse_targets_csv(b"image,target\na.jpg,2\na.jpg,NaN\n", "target"),
            {"a.jpg": 2.0},
        )

    def test_missing_and_nonnumeric_values_still_skipped(self) -> None:
        self.assertEqual(
            _parse_targets_csv(
                b"image,target\na.jpg,2\nb.jpg,\nc.jpg\n,3\nd.jpg,nope\ne.jpg,4,extra\n",
                "target",
            ),
            {"a.jpg": 2.0, "e.jpg": 4.0},
        )

    def test_missing_headers_still_raise(self) -> None:
        for data in (b"", b"image\na.jpg\n", b"target\n1\n"):
            with self.subTest(data=data):
                with self.assertRaises(RuntimeError):
                    _parse_targets_csv(data, "target")


if __name__ == "__main__":
    unittest.main()
