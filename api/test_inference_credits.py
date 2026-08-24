"""Inference deploy/predict billing: charge on user action, never twice."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.text = "{}"

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """Stands in for the Azure ML scoring call."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse({"predictions": [{"class_name": "tench", "confidence": 0.99}]})


class _FakeInferenceService:
    def __init__(self) -> None:
        self.deploy_calls = 0
        self.already_running = False

    def model_size_bytes(self, project_id: str, job_id: str) -> int:
        return 250 * 1024 * 1024

    def ensure_api_key(self, project_id: str, rotate: bool = False) -> str:
        return "vd_test_key"

    def register_and_deploy(self, project_id: str, job_id: str) -> bool:
        self.deploy_calls += 1
        return not self.already_running

    def deploy_status(self, project_id: str) -> dict[str, Any]:
        return {"status": "deploying"}


class InferenceCreditsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(cls._tmpdir.name, 'inf.db')}"
        os.environ["AUTH_ENABLED"] = "true"
        os.environ["AUTH_ALLOW_SIGNUP"] = "true"
        os.environ["AUTH_REQUIRE_EMAIL_VERIFY"] = "false"
        os.environ["SESSION_SECRET"] = "inference-credits-test-secret"
        os.environ["STORAGE_BACKEND"] = "local"
        os.environ["LOCAL_STORAGE_PATH"] = os.path.join(cls._tmpdir.name, "storage")
        os.environ["AZURE_ML_INFERENCE_VM"] = "Standard_F2s_v2"
        Path(os.environ["LOCAL_STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)
        for key in ("AUTH_USERNAME", "AUTH_PASSWORD", "BASIC_AUTH_USERNAME", "BASIC_AUTH_PASSWORD"):
            os.environ.pop(key, None)

        import db.database as database

        database._engine = None
        database._SessionLocal = None
        database.init_db()

        from fastapi.testclient import TestClient
        from main import app
        from routers import inference as inference_router
        from routers import projects as projects_router
        from services.project_store import ProjectStore

        projects_router.store = ProjectStore()
        inference_router._store = ProjectStore()
        cls.inference_router = inference_router
        cls.store = ProjectStore()
        cls.client = TestClient(app)

        email = "inference.credits@visiondock.test"
        cls.client.post(
            "/api/auth/register",
            json={"email": email, "password": "TestPass123!", "name": "Inference Credits"},
        )
        login = cls.client.post(
            "/api/auth/login", json={"username": email, "password": "TestPass123!"}
        )
        assert login.status_code == 200, login.text

        created = cls.client.post("/api/projects", json={"name": "Inference Billing"})
        cls.project_id = (created.json().get("project") or created.json())["id"]
        cls.job_id = f"visiondock-train-{cls.project_id}-20260813_085626"
        cls.store.update_meta(
            cls.project_id,
            {
                "training": {"job_id": cls.job_id, "status": "Completed"},
                "model": {"job_id": cls.job_id, "task_type": "classification"},
                "inference": {
                    "status": "deployed",
                    "scoring_uri": "https://example.invalid/score",
                    "aml_primary_key": "aml-key",
                    "task_type": "classification",
                },
            },
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        import db.database as database

        database._engine = None
        database._SessionLocal = None
        cls._tmpdir.cleanup()

    def _balance(self) -> int:
        return self.client.get("/api/credits/me").json()["data"]["balance"]

    def test_deploy_charges_from_model_size(self) -> None:
        from services.azure_pricing import inference_deploy_credits

        fake = _FakeInferenceService()
        self.inference_router.get_inference_service = lambda: fake
        expected, _ = inference_deploy_credits(
            model_bytes=250 * 1024 * 1024, vm_size="Standard_F2s_v2"
        )
        before = self._balance()

        res = self.client.post(f"/api/inference/{self.project_id}/deploy")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["credits"]["debited"], expected)
        self.assertEqual(self._balance(), before - expected)

    def test_deploy_already_running_is_free(self) -> None:
        fake = _FakeInferenceService()
        fake.already_running = True
        self.inference_router.get_inference_service = lambda: fake
        before = self._balance()

        res = self.client.post(f"/api/inference/{self.project_id}/deploy")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIsNone(res.json()["credits"])
        self.assertEqual(self._balance(), before)

    def test_predict_debits_one_credit(self) -> None:
        from services.credits import cost_for

        self.inference_router.httpx.AsyncClient = _FakeAsyncClient
        before = self._balance()

        res = self.client.post(
            f"/api/inference/{self.project_id}/predict",
            files={"file": ("img.jpg", b"not-a-real-jpeg", "image/jpeg")},
        )
        self.assertEqual(res.status_code, 200, res.text)
        cost = cost_for("inference_predict")
        self.assertEqual(res.json()["credits"]["debited"], cost)
        self.assertEqual(self._balance(), before - cost)


if __name__ == "__main__":
    unittest.main()
