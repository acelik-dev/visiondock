"""End-to-end credits + session + usage flow via FastAPI TestClient."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class CreditsE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls._tmpdir.name, "e2e.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["AUTH_ENABLED"] = "true"
        os.environ["AUTH_ALLOW_SIGNUP"] = "true"
        os.environ["SESSION_SECRET"] = "e2e-test-session-secret-not-for-prod"
        os.environ["AZURE_ML_VM_SIZE"] = "Standard_D4s_v3"
        os.environ["STORAGE_BACKEND"] = "local"
        os.environ["LOCAL_STORAGE_PATH"] = os.path.join(cls._tmpdir.name, "storage")
        os.environ["AUTH_REQUIRE_EMAIL_VERIFY"] = "false"
        os.environ.pop("AUTH_USERNAME", None)
        os.environ.pop("AUTH_PASSWORD", None)
        os.environ.pop("BASIC_AUTH_USERNAME", None)
        os.environ.pop("BASIC_AUTH_PASSWORD", None)

        # Reset DB engine so this process uses the isolated sqlite file.
        import db.database as database

        database._engine = None
        database._SessionLocal = None
        database.init_db()

        # Import app after env + DB are ready.
        from fastapi.testclient import TestClient
        from main import app
        from routers import projects as projects_router
        from routers import training as training_router
        from services.project_store import ProjectStore

        # Re-bind stores so LOCAL_STORAGE_PATH from this suite is used even if
        # another test class already imported the app.
        projects_router.store = ProjectStore()
        training_router._project_store = ProjectStore()

        cls.client = TestClient(app)
        cls.Session = database.get_session_factory()
        from services import azure_pricing as pricing

        cls.pricing = pricing

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        import db.database as database

        database._engine = None
        database._SessionLocal = None
        cls._tmpdir.cleanup()

    def test_01_register_creates_db_session(self) -> None:
        from db.models import User, UserSession

        r = self.client.post(
            "/api/auth/register",
            json={
                "email": "e2e.credits@visiondock.test",
                "password": "TestPass123!",
                "name": "E2E Credits",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        # Signup no longer opens a session; sign in after register (verify disabled in this suite).
        login = self.client.post(
            "/api/auth/login",
            json={"username": "e2e.credits@visiondock.test", "password": "TestPass123!"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        body = login.json()
        self.assertTrue(body.get("authenticated"))
        self.assertEqual(body.get("email"), "e2e.credits@visiondock.test")
        self.assertIsNotNone(body.get("user_id"))
        self.assertIsNotNone(body.get("session_id"), "login must persist UserSession id in cookie")

        db = self.Session()
        try:
            user = db.query(User).filter(User.email == "e2e.credits@visiondock.test").one()
            self.assertEqual(user.id, body["user_id"])
            self.assertEqual(int(user.credits_balance), 100)
            sessions = db.query(UserSession).filter(UserSession.user_id == user.id).all()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].id, body["session_id"])
            self.assertIsNone(sessions[0].revoked_at)
            self.assertEqual(sessions[0].auth_method, "password")
        finally:
            db.close()

    def test_02_credits_me_and_costs(self) -> None:
        me = self.client.get("/api/credits/me")
        self.assertEqual(me.status_code, 200, me.text)
        data = me.json()["data"]
        self.assertEqual(data["balance"], 100)
        self.assertEqual(data["plan"], "free")
        self.assertIn("vlm_analyze", data["costs"])
        self.assertEqual(data["costs"]["vlm_analyze"], self.pricing.action_credits("vlm_analyze"))
        self.assertEqual(
            data["costs"]["training_submit"],
            self.pricing.action_credits("training_submit"),
        )
        self.assertEqual(data["pricing"]["training_billing"], "charged_on_job_end")
        self.assertEqual(data["pricing"]["vm_size"], "Standard_D4s_v3")

        costs = self.client.get("/api/credits/costs")
        self.assertEqual(costs.status_code, 200, costs.text)
        cdata = costs.json()["data"]
        self.assertIn("azure_rates", cdata["pricing"])
        self.assertAlmostEqual(cdata["pricing"]["vm_hourly_usd"], 0.204, places=3)

    def test_03_debit_vlm_writes_usage_and_ledger(self) -> None:
        from db.models import CreditLedger, UsageEvent

        before = self.client.get("/api/credits/me").json()["data"]["balance"]
        cost = self.pricing.action_credits("vlm_analyze")

        # Hit a real authenticated debit path used by discovery chat.
        # If VLM keys are missing the route may fail after debit-or-before;
        # call service through a tiny internal endpoint substitute via credits helpers.
        from services.credits import require_and_debit
        from services.project_access import session_user

        # Simulate the same session cookie context as HTTP handlers.
        # Use TestClient request scope via a lightweight credits debit by activating
        # nothing — instead call /api/credits/me then debit in-process with session dict.
        me = self.client.get("/api/credits/me").json()["data"]
        session = {
            "email": me["email"],
            "user_id": me["user_id"],
            "session_id": me["session_id"],
        }
        db = self.Session()
        try:
            result = require_and_debit(
                db,
                session,
                "vlm_analyze",
                ref="e2e-vlm",
                note="e2e VLM debit",
                project_id="prj-e2e",
            )
            self.assertEqual(result["debited"], cost)
            self.assertEqual(result["balance"], before - cost)
            self.assertIsNotNone(result.get("azure_cost_usd"))
            self.assertGreater(result["azure_cost_usd"], 0)

            events = (
                db.query(UsageEvent)
                .filter(UsageEvent.user_id == me["user_id"], UsageEvent.action == "vlm_analyze")
                .all()
            )
            self.assertTrue(events)
            self.assertEqual(events[-1].session_id, me["session_id"])
            self.assertEqual(events[-1].credits_delta, -cost)
            self.assertEqual(events[-1].project_id, "prj-e2e")

            ledger = (
                db.query(CreditLedger)
                .filter(CreditLedger.user_id == me["user_id"], CreditLedger.reason == "vlm_analyze")
                .all()
            )
            self.assertTrue(ledger)
            self.assertEqual(ledger[-1].usage_event_id, events[-1].id)
        finally:
            db.close()

        after = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(after["balance"], before - cost)
        self.assertTrue(any(x["action"] == "vlm_analyze" for x in after["usage"]))
        self.assertTrue(any(x["reason"] == "vlm_analyze" for x in after["ledger"]))

    def test_04_http_generate_config_debit_or_check(self) -> None:
        """Exercise authenticated project create + credit check path."""
        r = self.client.post("/api/projects", json={"name": "E2E Credits Project"})
        # projects.create may return different shapes; accept 200/201
        self.assertIn(r.status_code, (200, 201), r.text)
        body = r.json()
        project = body.get("project") or body.get("data") or body
        project_id = project.get("id") if isinstance(project, dict) else None
        self.assertTrue(project_id)

        me = self.client.get("/api/credits/me").json()["data"]
        self.assertGreaterEqual(me["balance"], self.pricing.action_credits("generate_config"))

    def test_05_training_settle_from_azure_duration(self) -> None:
        from services.credits import settle_training_compute

        me = self.client.get("/api/credits/me").json()["data"]
        before = me["balance"]
        credits, usd = self.pricing.training_compute_credits(
            1800, vm_size="Standard_D4s_v3"
        )  # 30 minutes
        result = settle_training_compute(
            user_id=me["user_id"],
            job_id="visiondock-train-prj-e2e-20260101_000000",
            project_id="prj-e2e",
            duration_seconds=1800,
            vm_size="Standard_D4s_v3",
            job_status="Completed",
            session_id=me["session_id"],
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["debited"], credits)
        self.assertAlmostEqual(float(result["azure_cost_usd"]), usd, places=4)
        # 30 min * $0.204/hr = $0.102 → 11 credits
        self.assertEqual(credits, 11)

        after = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(after["balance"], before - credits)
        self.assertTrue(
            any(x["action"] == "training_compute" for x in after["usage"]),
            after["usage"],
        )
        train_usage = next(x for x in after["usage"] if x["action"] == "training_compute")
        self.assertEqual(train_usage["session_id"], me["session_id"])
        self.assertEqual(train_usage["credits_delta"], -credits)

        # Idempotent settle
        again = settle_training_compute(
            user_id=me["user_id"],
            job_id="visiondock-train-prj-e2e-20260101_000000",
            project_id="prj-e2e",
            duration_seconds=1800,
            vm_size="Standard_D4s_v3",
            job_status="Completed",
            session_id=me["session_id"],
        )
        self.assertIsNone(again)
        final = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(final["balance"], before - credits)

    def test_06_training_router_persist_settles(self) -> None:
        """Simulate AML status persist → settle for the owning user."""
        from routers.training import _maybe_settle_training_credits
        from services.project_store import ProjectStore

        me = self.client.get("/api/credits/me").json()["data"]
        before = me["balance"]
        store = ProjectStore()
        # Ensure project exists under temp storage
        os.environ["LOCAL_STORAGE_PATH"] = os.path.join(self._tmpdir.name, "storage")
        Path(os.environ["LOCAL_STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)

        # Create project via API (already may exist) or direct meta
        projects = self.client.get("/api/projects")
        self.assertEqual(projects.status_code, 200, projects.text)
        plist = projects.json()
        items = plist.get("projects") or plist.get("data") or plist
        if isinstance(items, dict):
            items = items.get("projects") or []
        project_id = items[0]["id"] if items else None
        if not project_id:
            created = self.client.post("/api/projects", json={"name": "Settle Project"})
            self.assertIn(created.status_code, (200, 201), created.text)
            body = created.json()
            project_id = (body.get("project") or body).get("id")

        job_id = f"visiondock-train-{project_id}-20260102_120000"
        meta = store.get_meta(project_id) or {}
        training = {
            "job_id": job_id,
            "status": "Running",
            "billed_user_id": me["user_id"],
            "billed_session_id": me["session_id"],
            "vm_size": "Standard_NC4as_T4_v3",
            "credits_settled": False,
        }
        store.update_meta(project_id, {"training": training})

        credits, usd = self.pricing.training_compute_credits(
            3600, vm_size="Standard_NC4as_T4_v3"
        )  # 1 hour T4
        self.assertEqual(credits, 56)  # ceil(0.558/0.01)=56
        self.assertAlmostEqual(usd, 0.558, places=3)

        _maybe_settle_training_credits(
            project_id=project_id,
            job_id=job_id,
            job_status="Completed",
            duration_seconds=3600,
            compute="gpu-cluster",
            prev_training=training,
        )

        after = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(after["balance"], before - credits)
        updated = (store.get_meta(project_id) or {}).get("training") or {}
        self.assertTrue(updated.get("credits_settled"))

        # Second call must not double-charge
        _maybe_settle_training_credits(
            project_id=project_id,
            job_id=job_id,
            job_status="Completed",
            duration_seconds=3600,
            compute="gpu-cluster",
            prev_training={**updated, "credits_settled": True},
        )
        final = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(final["balance"], before - credits)

    def test_06b_status_poll_keeps_billing_fields(self) -> None:
        """A status poll used to overwrite the training record and drop billed_user_id."""
        from routers.training import _persist_training_status
        from services.project_store import ProjectStore

        store = ProjectStore()
        me = self.client.get("/api/credits/me").json()["data"]
        before = me["balance"]

        created = self.client.post("/api/projects", json={"name": "Billing Fields"})
        self.assertIn(created.status_code, (200, 201), created.text)
        project_id = (created.json().get("project") or created.json()).get("id")
        job_id = f"visiondock-train-{project_id}-20260813_085626"

        store.update_meta(
            project_id,
            {
                "training": {
                    "job_id": job_id,
                    "status": "Submitting",
                    "billed_user_id": me["user_id"],
                    "billed_session_id": me["session_id"],
                    "vm_size": "Standard_D4s_v3",
                    "credits_settled": False,
                }
            },
        )

        # AML status payload carries no billing fields.
        _persist_training_status(
            {
                "job_id": job_id,
                "status": "Completed",
                "display_name": "VisionDock Training",
                "experiment": f"visiondock-{project_id}",
                "compute": "cpu-cluster",
                "duration_seconds": 595,
                "metrics": {"accuracy": 1.0},
            }
        )

        training = (store.get_meta(project_id) or {}).get("training") or {}
        self.assertEqual(training.get("billed_user_id"), me["user_id"])
        self.assertEqual(training.get("vm_size"), "Standard_D4s_v3")
        self.assertTrue(training.get("credits_settled"))

        credits, _ = self.pricing.training_compute_credits(595, vm_size="Standard_D4s_v3")
        after = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(after["balance"], before - credits)

    def test_07_activate_plan_and_402(self) -> None:
        from db.models import User

        r = self.client.post("/api/credits/activate-plan", json={"plan": "starter"})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual(data["plan"], "starter")
        self.assertEqual(data["granted"], 500)
        me = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(me["plan"], "starter")
        self.assertEqual(me["balance"], data["balance"])

        # Force low balance and assert 402 on expensive reserve check path.
        db = self.Session()
        try:
            user = db.query(User).filter(User.email == "e2e.credits@visiondock.test").one()
            user.credits_balance = 2
            db.commit()
        finally:
            db.close()

        from services.credits import require_balance

        me = self.client.get("/api/credits/me").json()["data"]
        session = {
            "email": me["email"],
            "user_id": me["user_id"],
            "session_id": me["session_id"],
        }
        db = self.Session()
        try:
            from fastapi import HTTPException

            with self.assertRaises(HTTPException) as ctx:
                require_balance(db, session, "training_submit")
            self.assertEqual(ctx.exception.status_code, 402)
        finally:
            db.close()

    def test_08_logout_revokes_session(self) -> None:
        from db.models import UserSession

        me = self.client.get("/api/credits/me").json()["data"]
        sid = me["session_id"]
        self.assertIsNotNone(sid)

        out = self.client.post("/api/auth/logout")
        self.assertEqual(out.status_code, 200, out.text)
        self.assertFalse(out.json().get("authenticated", True))

        db = self.Session()
        try:
            row = db.query(UserSession).filter(UserSession.id == int(sid)).one()
            self.assertIsNotNone(row.revoked_at)
        finally:
            db.close()

        # Cookie cleared → credits/me should 401
        me2 = self.client.get("/api/credits/me")
        self.assertEqual(me2.status_code, 401)

    def test_00_mock_training_submit_charges_compute(self) -> None:
        """HTTP training submit in mock mode settles Azure-mapped compute credits."""
        from services.project_store import ProjectStore

        email = "e2e.trainmock@visiondock.test"
        r = self.client.post(
            "/api/auth/register",
            json={"email": email, "password": "TestPass123!", "name": "Train Mock"},
        )
        if r.status_code == 409:
            r = self.client.post(
                "/api/auth/login",
                json={"username": email, "password": "TestPass123!"},
            )
        else:
            self.assertEqual(r.status_code, 200, r.text)
            r = self.client.post(
                "/api/auth/login",
                json={"username": email, "password": "TestPass123!"},
            )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(r.json().get("session_id"))

        created = self.client.post("/api/projects", json={"name": "Mock Train Proj"})
        self.assertIn(created.status_code, (200, 201), created.text)
        body = created.json()
        project_id = (body.get("project") or body).get("id")
        self.assertTrue(project_id)

        store = ProjectStore()
        store.update_meta(
            project_id,
            {
                "dataset": {
                    "uploaded": True,
                    "validated": True,
                    "mode": "classification",
                    "file_name": "train.zip",
                    "storage_key": f"projects/{project_id}/datasets/classification/",
                }
            },
        )

        before = self.client.get("/api/credits/me").json()["data"]["balance"]
        expected, _ = self.pricing.training_compute_credits(
            15 * 60, vm_size="Standard_D4s_v3"
        )

        os.environ["TRAINING_MOCK"] = "1"
        try:
            submit = self.client.post(
                "/api/training/submit",
                json={
                    "project_id": project_id,
                    "task_type": "classification",
                    "config": {"epochs": 1},
                },
            )
            self.assertEqual(submit.status_code, 200, submit.text)
            payload = submit.json()
            self.assertEqual(payload.get("mode"), "mock")
            credits = payload.get("credits") or {}
            self.assertEqual(credits.get("debited"), expected)
            self.assertEqual(credits.get("reason"), "training_compute")
        finally:
            os.environ.pop("TRAINING_MOCK", None)

        after = self.client.get("/api/credits/me").json()["data"]
        self.assertEqual(after["balance"], before - expected)
        self.assertTrue(any(x["action"] == "training_compute" for x in after["usage"]))


if __name__ == "__main__":
    unittest.main()
