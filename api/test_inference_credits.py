"""Inference deploy/predict billing: charge on user action, never twice."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


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

    def register_and_deploy(
        self,
        project_id: str,
        job_id: str,
        *,
        billing_factory=None,
    ) -> bool:
        self.deploy_calls += 1
        if self.already_running:
            return False
        if billing_factory is not None:
            billing_factory()
        return True

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

    def _billing_context(
        self,
        ref: str,
        project_id: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        from db.database import get_session_factory
        from db.models import User
        from services.credits import debit_for_user_id

        account = self.client.get("/api/credits/me").json()["data"]
        session_factory = get_session_factory()
        db = session_factory()
        try:
            user = db.query(User).filter(User.id == int(account["user_id"])).one()
            user_id = int(user.id)
        finally:
            db.close()
        debit = debit_for_user_id(
            user_id,
            "inference_deploy",
            ref=ref,
            amount=3,
            project_id=project_id or self.project_id,
            session_id=account.get("session_id"),
        )
        return {
            "user_id": user_id,
            "session_id": account.get("session_id"),
            "debit_usage_event_id": int(debit["usage_event_id"]),
        }, int(debit["usage_event_id"])

    def _wait_for_deploy(self, project_id: str) -> None:
        from services import inference_service

        deadline = time.monotonic() + 3
        while project_id in inference_service._deploy_inflight and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertNotIn(project_id, inference_service._deploy_inflight)

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

    def test_debit_failure_prevents_thread_start_and_clears_inflight(self) -> None:
        from services import inference_service
        from services.inference_service import InferenceService

        project_id = f"{self.project_id}-debit-failure"

        def fail_billing() -> dict[str, Any]:
            raise RuntimeError("debit failed")

        with patch.object(inference_service.threading, "Thread") as thread:
            with self.assertRaisesRegex(RuntimeError, "debit failed"):
                InferenceService(self.store).register_and_deploy(
                    project_id,
                    self.job_id,
                    billing_factory=fail_billing,
                )
        thread.assert_not_called()
        self.assertNotIn(project_id, inference_service._deploy_inflight)

    def test_background_failure_refunds_exact_debit_once(self) -> None:
        from db.database import get_session_factory
        from db.models import CreditLedger, UsageEvent
        from services import inference_service
        from services.credits import refund_debit_for_user_id
        from services.inference_service import InferenceService

        project_id = self.store.create(name="Failed inference deploy")["id"]
        before = self._balance()
        billing, debit_event_id = self._billing_context("background-failure", project_id)
        service = InferenceService(self.store)

        def fail_deploy(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("Azure deployment failed")

        service._register_and_deploy_sync = fail_deploy  # type: ignore[method-assign]
        self.assertTrue(
            service.register_and_deploy(
                project_id,
                self.job_id,
                billing_factory=lambda: billing,
            )
        )
        self._wait_for_deploy(project_id)
        self.assertEqual(self._balance(), before)

        session_factory = get_session_factory()
        db = session_factory()
        try:
            debit_event = db.query(UsageEvent).filter(UsageEvent.id == debit_event_id).one()
            refunds = (
                db.query(UsageEvent)
                .filter(
                    UsageEvent.action == "refund_inference_deploy",
                    UsageEvent.ref == f"usage_event:{debit_event_id}",
                )
                .all()
            )
            self.assertEqual(debit_event.status, "success")
            self.assertEqual(len(refunds), 1)
            self.assertEqual(refunds[0].credits_delta, 3)
            refund_ledger = (
                db.query(CreditLedger)
                .filter(
                    CreditLedger.user_id == int(billing["user_id"]),
                    CreditLedger.reason == "refund_inference_deploy",
                    CreditLedger.ref == f"usage_event:{debit_event_id}",
                )
                .all()
            )
            self.assertEqual(len(refund_ledger), 1)
            self.assertEqual(refund_ledger[0].delta, 3)
            self.assertEqual(refund_ledger[0].reason, "refund_inference_deploy")
            self.assertEqual(refund_ledger[0].ref, f"usage_event:{debit_event_id}")
            self.assertEqual(refund_ledger[0].usage_event_id, refunds[0].id)
            debit_ledger = (
                db.query(CreditLedger)
                .filter(CreditLedger.usage_event_id == debit_event_id)
                .one()
            )
            self.assertEqual(debit_ledger.delta, -3)
            self.assertEqual(debit_ledger.reason, "inference_deploy")
            self.assertEqual(debit_ledger.ref, "background-failure")
        finally:
            db.close()

        repeated = refund_debit_for_user_id(
            user_id=int(billing["user_id"]),
            debit_usage_event_id=debit_event_id,
            session_id=billing.get("session_id"),
        )
        self.assertEqual(repeated["refunded"], 0)
        self.assertEqual(self._balance(), before)

    def test_successful_background_deployment_does_not_refund(self) -> None:
        from db.database import get_session_factory
        from db.models import UsageEvent
        from services.inference_service import InferenceService

        project_id = f"{self.project_id}-success"
        before = self._balance()
        billing, debit_event_id = self._billing_context("background-success")
        service = InferenceService(self.store)
        service._register_and_deploy_sync = lambda *args, **kwargs: {}  # type: ignore[method-assign]

        self.assertTrue(
            service.register_and_deploy(
                project_id,
                self.job_id,
                billing_factory=lambda: billing,
            )
        )
        self._wait_for_deploy(project_id)
        self.assertEqual(self._balance(), before - 3)

        session_factory = get_session_factory()
        db = session_factory()
        try:
            refund = (
                db.query(UsageEvent)
                .filter(
                    UsageEvent.action == "refund_inference_deploy",
                    UsageEvent.ref == f"usage_event:{debit_event_id}",
                )
                .one_or_none()
            )
            self.assertIsNone(refund)
        finally:
            db.close()

    def test_thread_start_failure_refunds_and_clears_inflight(self) -> None:
        from db.database import get_session_factory
        from db.models import UsageEvent
        from services import inference_service
        from services.inference_service import InferenceService

        project_id = f"{self.project_id}-thread-failure"
        before = self._balance()
        captured: dict[str, Any] = {}

        class FailingThread:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def start(self) -> None:
                self_test.assertIn("debit_usage_event_id", captured)
                captured["start_called"] = True
                raise RuntimeError("thread failed to start")

        def bill() -> dict[str, Any]:
            billing, debit_event_id = self._billing_context("thread-start-failure")
            captured["debit_usage_event_id"] = debit_event_id
            return billing

        self_test = self
        with patch.object(inference_service.threading, "Thread", FailingThread):
            with self.assertRaisesRegex(RuntimeError, "thread failed to start"):
                InferenceService(self.store).register_and_deploy(
                    project_id,
                    self.job_id,
                    billing_factory=bill,
                )
        self.assertTrue(captured.get("start_called"))
        self.assertNotIn(project_id, inference_service._deploy_inflight)
        self.assertEqual(self._balance(), before)

        debit_event_id = int(captured["debit_usage_event_id"])
        session_factory = get_session_factory()
        db = session_factory()
        try:
            debit_event = db.query(UsageEvent).filter(UsageEvent.id == debit_event_id).one()
            refunds = (
                db.query(UsageEvent)
                .filter(
                    UsageEvent.action == "refund_inference_deploy",
                    UsageEvent.ref == f"usage_event:{debit_event_id}",
                )
                .all()
            )
            self.assertEqual(debit_event.action, "inference_deploy")
            self.assertEqual(debit_event.credits_delta, -3)
            self.assertEqual(debit_event.status, "success")
            self.assertEqual(len(refunds), 1)
            self.assertEqual(refunds[0].credits_delta, 3)
        finally:
            db.close()

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
