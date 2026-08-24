"""Model Library bootstrap must not lock catalog demo classes into the project."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class ModelBootstrapClassesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["STORAGE_BACKEND"] = "local"
        os.environ["LOCAL_STORAGE_PATH"] = os.path.join(self._tmpdir.name, "storage")
        Path(os.environ["LOCAL_STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)

        from services.marketplace_import import MarketplaceImportService
        from services.project_store import ProjectStore

        self.store = ProjectStore()
        self.project = self.store.create(name="Model Bootstrap", owner_email="t@test.local")
        self.project_id = self.project["id"]

        item = MagicMock()
        item.id = "efficientnet-imagenette"
        item.name = "EfficientNet · Image classification"
        item.task_type = "classification"
        item.architecture = "efficientnet_b0"
        item.classes = ["tench", "English springer", "cassette player", "chain saw", "church"]
        item.description = "Demo EfficientNet"
        item.input_resolution = "224x224"
        item.metrics = {"accuracy": 0.94}
        item.trained_on = "Imagenette"
        item.target_name = ""
        item.target_unit = ""

        marketplace = MagicMock()
        marketplace.get_model.return_value = item
        self.item = item
        self.svc = MarketplaceImportService(projects=self.store, marketplace=marketplace)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_spec_classes_empty_catalog_names_are_examples_only(self) -> None:
        result = self.svc.bootstrap_project_from_model(self.project_id, self.item.id)

        self.assertEqual(result["spec"]["task_type"], "classification")
        self.assertEqual(result["spec"]["classes"], [])
        self.assertIn("efficientnet", result["spec"]["recommended_model"].lower())

        meta = self.store.get_meta(self.project_id) or {}
        template = meta.get("model_template") or {}
        self.assertEqual(template.get("source"), "marketplace")
        self.assertEqual(template.get("example_classes"), self.item.classes)
        # Spec on disk must stay empty too.
        loaded = self.store.load_spec(self.project_id) or {}
        self.assertEqual(loaded.get("classes"), [])

    def test_detection_also_starts_without_voc_classes(self) -> None:
        self.item.id = "yolov8n-voc-detection"
        self.item.task_type = "object_detection"
        self.item.architecture = "yolov8n"
        self.item.classes = ["aeroplane", "bicycle", "bird"]
        result = self.svc.bootstrap_project_from_model(self.project_id, self.item.id)
        self.assertEqual(result["spec"]["task_type"], "object_detection")
        self.assertEqual(result["spec"]["classes"], [])
        self.assertEqual(
            (self.store.get_meta(self.project_id) or {}).get("model_template", {}).get("example_classes"),
            ["aeroplane", "bicycle", "bird"],
        )

    def test_regression_keeps_soft_target_default(self) -> None:
        self.item.id = "efficientnet-age-regression"
        self.item.task_type = "regression"
        self.item.architecture = "efficientnet_b0"
        self.item.classes = []
        self.item.target_name = "age"
        self.item.target_unit = "years"
        result = self.svc.bootstrap_project_from_model(self.project_id, self.item.id)
        self.assertEqual(result["spec"]["task_type"], "regression")
        self.assertEqual(result["spec"]["classes"], [])
        self.assertEqual(result["spec"]["target_name"], "age")


if __name__ == "__main__":
    unittest.main()
