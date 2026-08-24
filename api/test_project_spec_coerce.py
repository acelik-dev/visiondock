"""Regression tests for LLM-shaped ProjectSpec coercion."""

from __future__ import annotations

import unittest

from schemas.project_spec import (
    ProjectSpec,
    apply_resolved_task_type,
    coerce_known_task_type,
    coerce_spec_dict,
    parse_project_spec,
    _coerce_task_type,
)


def _base_payload() -> dict:
    return {
        "project_name": "Dog Cat Demo",
        "task_type": "classification",
        "recommended_model": "EfficientNet-B0",
        "description": "Classify dogs and cats",
        "classes": ["köpek", "kedi", "yok"],
    }


class ProjectSpecCoerceTests(unittest.TestCase):
    def test_resize_dict_coerced(self) -> None:
        raw = {
            **_base_payload(),
            "preprocessing": {
                "resize": {
                    "method": "bilinear",
                    "target_size": "224x224",
                    "keep_aspect_ratio": False,
                }
            },
        }
        spec = parse_project_spec(raw)
        self.assertEqual(spec.preprocessing.resize, "224x224")
        self.assertEqual(spec.training_config.image_size, "224x224")

    def test_normalize_true_coerced(self) -> None:
        raw = {**_base_payload(), "preprocessing": {"normalize": True}}
        spec = parse_project_spec(raw)
        self.assertEqual(spec.preprocessing.normalize["mean"], [0.485, 0.456, 0.406])
        self.assertEqual(spec.preprocessing.normalize["std"], [0.229, 0.224, 0.225])

    def test_export_format_string_coerced(self) -> None:
        raw = {
            **_base_payload(),
            "postprocessing": {
                "export_format": "CSV_with_filename_label_confidence",
            },
        }
        spec = parse_project_spec(raw)
        self.assertEqual(spec.postprocessing.export_format, ["onnx", "torchscript"])

    def test_direct_model_validate_with_llm_shapes(self) -> None:
        raw = {
            **_base_payload(),
            "preprocessing": {
                "resize": {"target_size": "224x224"},
                "normalize": True,
            },
            "postprocessing": {
                "export_format": "CSV_with_filename_label_confidence",
            },
        }
        spec = ProjectSpec.model_validate(raw)
        self.assertEqual(spec.preprocessing.resize, "224x224")
        self.assertIsInstance(spec.preprocessing.normalize, dict)
        self.assertEqual(
            spec.postprocessing.export_format,
            ["CSV_with_filename_label_confidence"],
        )

    def test_combined_user_error_payload(self) -> None:
        raw = {
            **_base_payload(),
            "preprocessing": {
                "resize": {
                    "method": "bilinear",
                    "target_size": "224x224",
                    "keep_aspect_ratio": False,
                },
                "normalize": True,
            },
            "postprocessing": {
                "export_format": "CSV_with_filename_label_confidence",
            },
        }
        spec = parse_project_spec(raw)
        self.assertEqual(spec.preprocessing.resize, "224x224")
        self.assertEqual(spec.preprocessing.normalize["mean"], [0.485, 0.456, 0.406])
        self.assertEqual(spec.postprocessing.export_format, ["onnx", "torchscript"])

    def test_classes_string_coerced(self) -> None:
        raw = {**_base_payload(), "classes": "köpek, kedi, yok"}
        spec = parse_project_spec(raw)
        self.assertEqual(spec.classes, ["köpek", "kedi", "yok"])

    def test_coerce_spec_dict_without_validation_errors(self) -> None:
        raw = {
            **_base_payload(),
            "preprocessing": {"normalize": True},
            "postprocessing": {"export_format": "onnx"},
        }
        coerced = coerce_spec_dict(raw)
        ProjectSpec.model_validate(coerced)

    def test_augmentation_dict_and_gpu_object_coerced(self) -> None:
        raw = {
            **_base_payload(),
            "task_type": "object_detection",
            "recommended_model": "YOLOv8m",
            "classes": ["jumper", "canopy", "landing", "malfunction"],
            "training_config": {
                "epochs": 50,
                "batch_size": 16,
                "augmentation": {
                    "mosaic": True,
                    "mixup": False,
                    "cutmix": False,
                    "color_jitter": True,
                },
            },
            "hardware_requirements": {
                "gpu": {
                    "count": 1,
                    "type": "NVIDIA T4 or equivalent",
                    "memory_gb": 24,
                },
            },
        }
        spec = parse_project_spec(raw)
        self.assertTrue(spec.training_config.augmentation)
        self.assertFalse(spec.training_config.mixup)
        self.assertFalse(spec.training_config.cutmix)
        self.assertIn("NVIDIA T4", spec.hardware_requirements.gpu)
        self.assertEqual(spec.hardware_requirements.vram_gb, 24)

    def test_invalid_task_type_falls_back(self) -> None:
        raw = {**_base_payload(), "task_type": "image classification"}
        spec = parse_project_spec(raw)
        self.assertEqual(spec.task_type, "classification")

    def test_only_exact_task_enums(self) -> None:
        self.assertEqual(_coerce_task_type("object detection"), "object_detection")
        self.assertEqual(_coerce_task_type("multi-label"), "multi_label")
        self.assertEqual(_coerce_task_type("image_recognition"), "classification")

    def test_vlm_task_lock_overrides_wrong_json(self) -> None:
        spec = parse_project_spec({**_base_payload(), "task_type": "multi_label"})
        locked = apply_resolved_task_type(spec, "classification")
        self.assertEqual(locked.task_type, "classification")
        self.assertEqual(coerce_known_task_type("object detection"), "object_detection")
        self.assertIsNone(coerce_known_task_type("single-label classification"))
        self.assertIsNone(coerce_known_task_type("not-a-task"))


if __name__ == "__main__":
    unittest.main()
