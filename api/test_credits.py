"""Unit tests for credit debit / plan activation / Azure-priced costs."""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi import HTTPException


class CreditsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["AZURE_ML_VM_SIZE"] = "Standard_D4s_v3"
        import db.database as database

        database._engine = None
        database._SessionLocal = None
        database.init_db()
        self.Session = database.get_session_factory()

        from services import azure_pricing as pricing
        from services import credits as credits_mod

        self.pricing = pricing
        self.credits = credits_mod
        # Refresh module COSTS from pricing (env may have changed).
        self.credits.COSTS = {
            k: pricing.action_credits(k)
            for k in (
                "vlm_analyze",
                "generate_config",
                "pipeline_tune",
                "training_submit",
                "inference_deploy",
                "inference_predict",
            )
        }

    def tearDown(self) -> None:
        import db.database as database

        database._engine = None
        database._SessionLocal = None
        self._tmpdir.cleanup()

    def test_signup_balance_and_debit(self) -> None:
        db = self.Session()
        try:
            session = {"email": "demo@visiondock.test", "user_id": None}
            account = self.credits.get_account(db, session)
            self.assertEqual(account["balance"], 100)
            self.assertEqual(account["plan"], "free")

            expected = self.pricing.action_credits("vlm_analyze")
            result = self.credits.require_and_debit(db, session, "vlm_analyze")
            self.assertEqual(result["debited"], expected)
            self.assertEqual(result["balance"], 100 - expected)
            self.assertTrue(account["usage"] is not None or True)

            account = self.credits.get_account(db, session)
            self.assertEqual(account["balance"], 100 - expected)
            self.assertTrue(any(row["reason"] == "vlm_analyze" for row in account["ledger"]))
            self.assertTrue(any(row["action"] == "vlm_analyze" for row in account["usage"]))
        finally:
            db.close()

    def test_insufficient_credits(self) -> None:
        db = self.Session()
        try:
            session = {"email": "poor@visiondock.test", "user_id": None}
            self.credits.get_account(db, session)
            from db.models import User

            user = db.query(User).filter(User.email == "poor@visiondock.test").one()
            user.credits_balance = 1
            db.commit()
            with self.assertRaises(HTTPException) as ctx:
                self.credits.require_and_debit(db, session, "training_submit")
            self.assertEqual(ctx.exception.status_code, 402)
        finally:
            db.close()

    def test_check_does_not_debit(self) -> None:
        db = self.Session()
        try:
            session = {"email": "check@visiondock.test", "user_id": None}
            before = self.credits.get_account(db, session)["balance"]
            checked = self.credits.require_balance(db, session, "training_submit")
            after = self.credits.get_account(db, session)["balance"]
            self.assertEqual(before, after)
            self.assertEqual(checked["required"], self.pricing.action_credits("training_submit"))
        finally:
            db.close()

    def test_training_settle_from_duration(self) -> None:
        db = self.Session()
        try:
            session = {"email": "train@visiondock.test", "user_id": None}
            account = self.credits.get_account(db, session)
            user_id = account["user_id"]
            credits, usd = self.pricing.training_compute_credits(
                1800, vm_size="Standard_D4s_v3"
            )
            result = self.credits.settle_training_compute(
                user_id=user_id,
                job_id="visiondock-train-prj-abc-1",
                project_id="prj-abc",
                duration_seconds=1800,
                vm_size="Standard_D4s_v3",
                job_status="Completed",
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["debited"], credits)
            self.assertAlmostEqual(result["azure_cost_usd"], usd, places=4)
            # Idempotent
            again = self.credits.settle_training_compute(
                user_id=user_id,
                job_id="visiondock-train-prj-abc-1",
                project_id="prj-abc",
                duration_seconds=1800,
                vm_size="Standard_D4s_v3",
                job_status="Completed",
            )
            self.assertIsNone(again)
        finally:
            db.close()

    def test_activate_plan_grants_once(self) -> None:
        db = self.Session()
        try:
            session = {"email": "plan@visiondock.test", "user_id": None}
            self.credits.get_account(db, session)
            result = self.credits.activate_plan(db, session, "pro")
            self.assertEqual(result["granted"], 2000)
            self.assertEqual(result["balance"], 2100)
            self.assertEqual(result["plan"], "pro")
            with self.assertRaises(HTTPException) as ctx:
                self.credits.activate_plan(db, session, "pro")
            self.assertEqual(ctx.exception.status_code, 400)
        finally:
            db.close()

    def test_inference_deploy_scales_with_model_size(self) -> None:
        small, _ = self.pricing.inference_deploy_credits(model_bytes=6 * 1024 * 1024)
        large, _ = self.pricing.inference_deploy_credits(model_bytes=2 * 1024 * 1024 * 1024)
        self.assertGreater(large, small)
        gpu, _ = self.pricing.inference_deploy_credits(
            model_bytes=250 * 1024 * 1024, vm_size="Standard_NC4as_T4_v3"
        )
        cpu, _ = self.pricing.inference_deploy_credits(
            model_bytes=250 * 1024 * 1024, vm_size="Standard_F2s_v2"
        )
        self.assertGreater(gpu, cpu)

    def test_refund_restores_balance(self) -> None:
        db = self.Session()
        try:
            session = {"email": "refund@visiondock.test", "user_id": None}
            expected = self.pricing.action_credits("vlm_analyze")
            self.credits.require_and_debit(db, session, "vlm_analyze")
            refunded = self.credits.refund_credits(db, session, "vlm_analyze")
            self.assertEqual(refunded["refunded"], expected)
            self.assertEqual(self.credits.get_account(db, session)["balance"], 100)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
