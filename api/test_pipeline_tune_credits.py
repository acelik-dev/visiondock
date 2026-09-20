"""Auto-tune billing: only a real VLM run costs credits, not a page revisit."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any


class PipelineTuneCreditsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(cls._tmpdir.name, 'tune.db')}"
        os.environ["AUTH_ENABLED"] = "true"
        os.environ["AUTH_ALLOW_SIGNUP"] = "true"
        os.environ["AUTH_REQUIRE_EMAIL_VERIFY"] = "false"
        os.environ["SESSION_SECRET"] = "pipeline-tune-credits-test-secret"
        os.environ["STORAGE_BACKEND"] = "local"
        os.environ["LOCAL_STORAGE_PATH"] = os.path.join(cls._tmpdir.name, "storage")
        Path(os.environ["LOCAL_STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)
        for key in ("AUTH_USERNAME", "AUTH_PASSWORD", "BASIC_AUTH_USERNAME", "BASIC_AUTH_PASSWORD"):
            os.environ.pop(key, None)

        import db.database as database

        database._engine = None
        database._SessionLocal = None
        database.init_db()

        from fastapi.testclient import TestClient
        from main import app
        from routers import projects as projects_router
        from services.project_store import ProjectStore

        projects_router.store = ProjectStore()
        cls.store = ProjectStore()
        cls.client = TestClient(app)

        email = "tune.credits@visiondock.test"
        cls.client.post(
            "/api/auth/register",
            json={"email": email, "password": "TestPass123!", "name": "Tune Credits"},
        )
        login = cls.client.post(
            "/api/auth/login", json={"username": email, "password": "TestPass123!"}
        )
        assert login.status_code == 200, login.text

        created = cls.client.post("/api/projects", json={"name": "Tune Billing"})
        cls.project_id = (created.json().get("project") or created.json())["id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        import db.database as database

        database._engine = None
        database._SessionLocal = None
        cls._tmpdir.cleanup()

    def _balance(self) -> int:
        return self.client.get("/api/credits/me").json()["data"]["balance"]

    def _patch_tune(self, result: dict[str, Any]) -> None:
        import services.pipeline_tuning as tuning

        if not hasattr(self, "_orig_tune"):
            self._orig_tune = tuning.tune_pipeline_from_dataset
        tuning.tune_pipeline_from_dataset = lambda project_id, force=False: result

    def tearDown(self) -> None:
        import services.pipeline_tuning as tuning

        if hasattr(self, "_orig_tune"):
            tuning.tune_pipeline_from_dataset = self._orig_tune

    def test_fresh_tune_charges(self) -> None:
        self._patch_tune({"success": True, "cached": False, "spec": {}})
        before = self._balance()

        res = self.client.post(f"/api/projects/{self.project_id}/pipeline/tune")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["credits"]["debited"], 1)
        self.assertEqual(self._balance(), before - 1)

    def test_cached_tune_is_free(self) -> None:
        """Re-entering the configuration step must not cost anything."""
        self._patch_tune({"success": True, "cached": True, "spec": {}})
        before = self._balance()

        for _ in range(3):
            res = self.client.post(f"/api/projects/{self.project_id}/pipeline/tune")
            self.assertEqual(res.status_code, 200, res.text)
            self.assertIsNone(res.json().get("credits"))
        self.assertEqual(self._balance(), before)

    def test_unchanged_dataset_returns_cached_without_vlm(self) -> None:
        """The stored fingerprint short-circuits before any VLM client is built."""
        from services.pipeline_tuning import _pipeline_tune_fingerprint, tune_pipeline_from_dataset

        project_id = (
            self.client.post("/api/projects", json={"name": "Fingerprint"}).json()["project"]["id"]
        )
        self.store.save_spec(
            project_id,
            {
                "task_type": "classification",
                "classes": ["a", "b"],
                "project_name": "Fingerprint",
                "recommended_model": "EfficientNet-B0",
            },
        )
        self.store.update_meta(project_id, {"dataset": {"file_name": "set.zip", "validated": True}})
        meta = self.store.get_meta(project_id) or {}
        self.store.update_meta(
            project_id, {"pipeline_tune_fingerprint": _pipeline_tune_fingerprint(meta)}
        )

        os.environ.pop("VLM_API_KEY", None)
        result = tune_pipeline_from_dataset(project_id)
        self.assertTrue(result["cached"])

    def test_skills_prompt_section_is_a_strict_catalog(self) -> None:
        from services.pipeline_tuning import _skills_prompt_section

        section = _skills_prompt_section("classification")
        self.assertIn("AVAILABLE PIPELINE SKILLS", section)
        self.assertIn("enabled_skills_enum:", section)
        self.assertIn("pre.resize", section)

    def test_catalog_stamp_changes_tune_fingerprint(self) -> None:
        from services.pipeline_tuning import _pipeline_tune_fingerprint
        from services.skills_store import get_skills_store

        meta = {"dataset": {"file_name": "set.zip", "validated": True}}
        store = get_skills_store()
        before = _pipeline_tune_fingerprint(meta)
        catalog = store.get_catalog(refresh=True)
        store.save_catalog(catalog)
        after = _pipeline_tune_fingerprint(meta)
        self.assertNotEqual(before, after)
