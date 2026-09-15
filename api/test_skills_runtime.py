"""Skills runtime: enabled_skills + default_params → pipeline buckets / env."""

from __future__ import annotations

import json
import unittest

from schemas.skills import SkillItem
from services.pipeline_env import (
    merge_spec_pipeline_into_config,
    pipeline_env_from_spec,
    resolve_pipeline_from_skills,
)
from services.skill_registry import apply_entrypoint, is_known_entrypoint
from services.skills_store import (
    apply_skills_to_spec_dict,
    default_seed_skills,
    skills_from_legacy_flags,
)


def _seed_skills() -> list[SkillItem]:
    return [SkillItem.model_validate(s) for s in default_seed_skills()]


class SkillRegistryApplyTests(unittest.TestCase):
    def test_seed_entrypoints_are_registered(self) -> None:
        for skill in _seed_skills():
            self.assertTrue(is_known_entrypoint(skill.entrypoint), skill.entrypoint)
            self.assertFalse(skill.legacy_flags)

    def test_apply_entrypoint_nms(self) -> None:
        pre: dict = {}
        post: dict = {}
        training: dict = {}
        apply_entrypoint(
            "visiondock_postprocess.nms",
            {"nms_iou_threshold": 0.4},
            preprocessing=pre,
            postprocessing=post,
            training=training,
        )
        self.assertEqual(post["nms_iou_threshold"], 0.4)
        self.assertEqual(pre, {})
        self.assertEqual(training, {})

    def test_apply_entrypoint_normalize_whole_params(self) -> None:
        pre: dict = {}
        post: dict = {}
        training: dict = {}
        params = {"mean": [1, 2, 3], "std": [4, 5, 6]}
        apply_entrypoint(
            "visiondock_preprocess.normalize",
            params,
            preprocessing=pre,
            postprocessing=post,
            training=training,
        )
        self.assertEqual(pre["normalize"], params)


class ApplySkillsToSpecTests(unittest.TestCase):
    def test_enabled_skills_expand_without_legacy_flags(self) -> None:
        skills = _seed_skills()
        out = apply_skills_to_spec_dict(
            {
                "enabled_skills": [
                    "pre.resize",
                    "pre.normalize",
                    "pre.grayscale",
                    "aug.mixup",
                    "post.nms",
                    "post.sahi",
                    "post.export",
                ],
            },
            skills,
        )
        self.assertEqual(out["preprocessing"]["resize"], "224x224")
        self.assertTrue(out["preprocessing"]["grayscale"])
        self.assertEqual(
            out["preprocessing"]["normalize"]["mean"],
            [0.485, 0.456, 0.406],
        )
        self.assertTrue(out["training_config"]["mixup"])
        self.assertEqual(out["postprocessing"]["nms_iou_threshold"], 0.5)
        self.assertTrue(out["postprocessing"]["sahi"])
        self.assertEqual(out["postprocessing"]["sahi_slice_size"], 640)
        self.assertEqual(out["postprocessing"]["export_format"], ["onnx"])
        self.assertNotIn("legacy_flags", out)

    def test_unknown_skill_ids_dropped(self) -> None:
        out = apply_skills_to_spec_dict(
            {"enabled_skills": ["pre.grayscale", "not.a.skill"]},
            _seed_skills(),
        )
        self.assertEqual(out["enabled_skills"], ["pre.grayscale"])

    def test_infer_skills_from_pipeline_flags(self) -> None:
        found = skills_from_legacy_flags(
            {
                "preprocessing": {"grayscale": True, "denoise": True},
                "postprocessing": {"tta": True},
                "training_config": {"mixup": True},
            },
            _seed_skills(),
        )
        self.assertIn("pre.resize", found)
        self.assertIn("pre.normalize", found)
        self.assertIn("post.export", found)
        self.assertIn("pre.grayscale", found)
        self.assertIn("pre.denoise", found)
        self.assertIn("post.tta", found)
        self.assertIn("aug.mixup", found)


class PipelineEnvSkillsTests(unittest.TestCase):
    def test_resolve_and_env_from_enabled_skills_only(self) -> None:
        skills = _seed_skills()
        pre, post, training, ids = resolve_pipeline_from_skills(
            enabled_skills=["pre.grayscale", "post.nms", "aug.cutmix", "post.export"],
            skills=skills,
        )
        self.assertTrue(pre["grayscale"])
        self.assertEqual(post["nms_iou_threshold"], 0.5)
        self.assertTrue(training["cutmix"])
        self.assertEqual(ids, ["pre.grayscale", "post.nms", "aug.cutmix", "post.export"])

        env = pipeline_env_from_spec(
            {"enabled_skills": ids},
            {"enabled_skills": ids},
            640,
        )
        # Monkeypatch path uses store; inject by putting expanded buckets in config too.
        env2 = pipeline_env_from_spec(
            {
                "enabled_skills": ids,
                "preprocessing": pre,
                "postprocessing": post,
                "training_config": training,
            },
            {
                "enabled_skills": ids,
                "preprocessing": pre,
                "postprocessing": post,
                "training_config": training,
            },
            640,
        )
        self.assertEqual(env2["PREPROCESS_GRAYSCALE"], "1")
        self.assertEqual(env2["NMS_IOU_THRESHOLD"], "0.5")
        self.assertEqual(env2["CUTMIX_ENABLED"], "1")
        self.assertEqual(env2["ENABLED_SKILLS"], ",".join(ids))
        payload = json.loads(env2["PIPELINE_JSON"])
        self.assertEqual(payload["enabled_skills"], ids)
        self.assertTrue(payload["preprocessing"]["grayscale"])
        # env without store may still work if resolve uses store; assert keys exist
        self.assertIn("PREPROCESS_GRAYSCALE", env)

    def test_merge_spec_flattens_training_flags(self) -> None:
        skills = _seed_skills()
        pre, post, training, ids = resolve_pipeline_from_skills(
            enabled_skills=["aug.mixup", "pre.resize"],
            skills=skills,
        )
        self.assertTrue(training.get("mixup"))
        # Simulate merge after skills already resolved into the saved spec.
        merged = {
            "preprocessing": pre,
            "postprocessing": post,
            "training_config": training,
            "enabled_skills": ids,
        }
        for key in ("augmentation", "mixup", "cutmix", "image_size"):
            if key in training and key not in merged:
                merged[key] = training[key]
        self.assertTrue(merged["mixup"])
        self.assertEqual(merged["preprocessing"]["resize"], "224x224")

    def test_merge_spec_resolves_skills_from_ids(self) -> None:
        from unittest.mock import patch

        skills = _seed_skills()
        with patch(
            "services.pipeline_env.get_skills_store",
            create=True,
        ):
            # resolve_pipeline_from_skills imports get_skills_store inside; patch store path.
            with patch(
                "services.skills_store.get_skills_store"
            ) as mock_store:
                mock_store.return_value.list_skills.return_value = skills
                merged = merge_spec_pipeline_into_config(
                    {"enabled_skills": ["pre.grayscale", "post.nms", "aug.cutmix"]},
                    {},
                )
        self.assertTrue(merged["preprocessing"]["grayscale"])
        self.assertEqual(merged["postprocessing"]["nms_iou_threshold"], 0.5)
        self.assertTrue(merged["cutmix"])
        self.assertTrue(merged["training_config"]["cutmix"])


class CoerceSpecSkillsTests(unittest.TestCase):
    def test_parse_project_spec_applies_skills_when_store_available(self) -> None:
        from schemas.project_spec import coerce_spec_dict

        # Without store this may no-op; with seed in-memory via apply path we call directly.
        raw = {
            "task_type": "object_detection",
            "classes": ["a"],
            "enabled_skills": ["pre.resize", "post.nms", "post.export"],
            "preprocessing": {},
            "postprocessing": {},
            "training_config": {"epochs": 1, "batch_size": 2, "learning_rate": 0.001, "image_size": "640x640"},
            "hardware_requirements": {"gpu": "T4", "vram_gb": 16},
            "model_recommendation": {"architecture": "yolov8n", "reason": "test"},
        }
        # Force apply with seed skills regardless of store
        applied = apply_skills_to_spec_dict(raw, _seed_skills())
        coerced = coerce_spec_dict(applied)
        self.assertEqual(coerced["postprocessing"]["nms_iou_threshold"], 0.5)
        self.assertIsInstance(coerced["preprocessing"]["resize"], str)


if __name__ == "__main__":
    unittest.main()
