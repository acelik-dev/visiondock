"""Regression coverage for preserving annotated YOLO datasets before training."""

from __future__ import annotations

import base64
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


_JPEG_1X1 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/"
    "8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//"
    "8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//"
    "8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EB//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/"
    "9oACAECAQE/EB//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EB//2Q=="
)


def _load_aml_train_yolo():
    """Load the AML script without installing or starting Azure/Ultralytics."""
    azure_blob = types.ModuleType("azure.storage.blob")
    azure_blob.BlobServiceClient = object
    ultralytics = types.ModuleType("ultralytics")
    ultralytics.YOLO = object

    module_stubs = {
        "azure": types.ModuleType("azure"),
        "azure.storage": types.ModuleType("azure.storage"),
        "azure.storage.blob": azure_blob,
        "ultralytics": ultralytics,
    }
    previous = {name: sys.modules.get(name) for name in module_stubs}
    sys.modules.update(module_stubs)
    try:
        script = Path(__file__).parent / "training_scripts" / "aml_train_yolo.py"
        spec = importlib.util.spec_from_file_location("aml_train_yolo_under_test", script)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load {script}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


class YoloDatasetPreparationTests(unittest.TestCase):
    def test_preparation_preserves_images_labels_and_original_layout(self) -> None:
        aml_train_yolo = _load_aml_train_yolo()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "visiondock_dataset"
            for relative in (
                "images/train/a.jpg",
                "images/val/b.jpg",
                "labels/train/a.txt",
                "labels/val/b.txt",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".txt":
                    path.write_text("0 0.5 0.5 0.25 0.25\n", encoding="utf-8")
                else:
                    path.write_bytes(_JPEG_1X1)

            (root / "data.yaml").write_text(
                "train: images/train\nval: images/val\nnames: [widget]\n",
                encoding="utf-8",
            )

            prepared_yaml = aml_train_yolo._prepare_yolo_dataset(root)
            prepared = yaml.safe_load(prepared_yaml.read_text(encoding="utf-8"))

            self.assertEqual(Path(prepared["train"]), (root / "images/train").resolve())
            self.assertEqual(Path(prepared["val"]), (root / "images/val").resolve())
            self.assertTrue((root / "labels/train/a.txt").is_file())
            self.assertTrue((root / "labels/val/b.txt").is_file())
            self.assertTrue((root / "images/train/a.jpg").is_file())
            self.assertTrue((root / "images/val/b.jpg").is_file())
            self.assertFalse((root.parent / "visiondock_dataset_preprocessed").exists())

    def test_main_passes_preserved_dataset_yaml_to_yolo_train(self) -> None:
        aml_train_yolo = _load_aml_train_yolo()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "visiondock_dataset"
            for relative in (
                "images/train/a.jpg",
                "images/val/b.jpg",
                "labels/train/a.txt",
                "labels/val/b.txt",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".txt":
                    path.write_text("0 0.5 0.5 0.25 0.25\n", encoding="utf-8")
                else:
                    path.write_bytes(_JPEG_1X1)
            (root / "data.yaml").write_text(
                "train: images/train\nval: images/val\nnames: [widget]\n",
                encoding="utf-8",
            )

            train_calls: list[dict] = []

            class FakeYolo:
                def __init__(self, _weights: str) -> None:
                    pass

                def train(self, **kwargs):
                    train_calls.append(kwargs)
                    return types.SimpleNamespace(results_dict={})

            preprocess_module = types.ModuleType("visiondock_preprocess")
            preprocess_module.preprocess_config_from_env = lambda: types.SimpleNamespace(
                to_dict=lambda: {}
            )
            postprocess_module = types.ModuleType("visiondock_postprocess")
            postprocess_module.load_postprocess_config = lambda: types.SimpleNamespace(
                to_dict=lambda: {}
            )

            with (
                patch.object(aml_train_yolo, "_download_dataset_zip", return_value=root),
                patch.object(aml_train_yolo, "YOLO", FakeYolo),
                patch.object(aml_train_yolo, "_log_metrics"),
                patch.object(aml_train_yolo, "tune_detection_thresholds", return_value={}),
                patch.object(aml_train_yolo, "_export_artifacts", return_value={}),
                patch.dict(
                    sys.modules,
                    {
                        "visiondock_preprocess": preprocess_module,
                        "visiondock_postprocess": postprocess_module,
                    },
                ),
            ):
                aml_train_yolo.main()

            self.assertEqual(len(train_calls), 1)
            training_yaml = Path(train_calls[0]["data"])
            training_config = yaml.safe_load(training_yaml.read_text(encoding="utf-8"))
            self.assertEqual(Path(training_config["train"]), (root / "images/train").resolve())
            self.assertEqual(Path(training_config["val"]), (root / "images/val").resolve())
            self.assertTrue((root / "labels/train/a.txt").is_file())
            self.assertTrue((root / "labels/val/b.txt").is_file())
            self.assertFalse((root.parent / "visiondock_dataset_preprocessed").exists())


if __name__ == "__main__":
    unittest.main()
