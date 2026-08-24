"""Class names come from the model; Generate Config only trims and de-duplicates them."""

from __future__ import annotations

import unittest
from types import SimpleNamespace


def _load_main_helpers():
    import os

    os.environ.setdefault("STORAGE_BACKEND", "local")
    os.environ.setdefault("AUTH_ENABLED", "false")
    from main import _dedupe_labels, _merge_spec_classes  # noqa: WPS433
    from schemas.project_spec import ProjectSpec

    return SimpleNamespace(
        dedupe=_dedupe_labels,
        merge=_merge_spec_classes,
        ProjectSpec=ProjectSpec,
    )


def _spec(cls, classes: list[str]):
    return cls.model_validate(
        {
            "project_name": "t",
            "task_type": "classification",
            "description": "d",
            "recommended_model": "EfficientNet-B0",
            "classes": classes,
        }
    )


class LabelHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = _load_main_helpers()

    def test_dedupe_trims_and_keeps_order(self):
        self.assertEqual(self.h.dedupe([" OK ", "Defect", "ok", ""]), ["OK", "Defect"])

    def test_no_word_filtering(self):
        """Words that used to be banned (drone, camera, images) must survive."""
        labels = ["drone", "camera drone", "aerial images", "traffic light"]
        self.assertEqual(self.h.dedupe(labels), labels)

    def test_multi_word_labels_survive(self):
        labels = ["kırmızı ışık ihlali", "yaya geçidi ihlali"]
        self.assertEqual(self.h.dedupe(labels), labels)

    def test_merge_is_a_union_not_a_filter(self):
        spec = _spec(self.h.ProjectSpec, ["OK", "Defect"])
        merged = self.h.merge(spec, ["Defect", "Scratch"])
        self.assertEqual(merged.classes, ["OK", "Defect", "Scratch"])

    def test_merge_keeps_spec_untouched_when_nothing_new(self):
        spec = _spec(self.h.ProjectSpec, ["OK", "Defect"])
        self.assertIs(self.h.merge(spec, ["ok"]), spec)


if __name__ == "__main__":
    unittest.main()
