"""E2E auth: signup email gate, DB sessions, verify, revoke."""

from __future__ import annotations

import os
import re
import tempfile
import unittest


class AuthE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls._tmpdir.name, "auth-e2e.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["AUTH_ENABLED"] = "true"
        os.environ["AUTH_ALLOW_SIGNUP"] = "true"
        os.environ["AUTH_DB_USERS"] = "true"
        os.environ["AUTH_REQUIRE_EMAIL_VERIFY"] = "true"
        os.environ["SESSION_SECRET"] = "auth-e2e-session-secret"
        os.environ["FRONTEND_URL"] = "http://localhost:8080"
        os.environ["PUBLIC_API_URL"] = "http://testserver"
        os.environ.pop("SMTP_HOST", None)
        os.environ.pop("EMAIL_FROM", None)
        os.environ.pop("AUTH_USERNAME", None)
        os.environ.pop("AUTH_PASSWORD", None)

        import db.database as database

        database._engine = None
        database._SessionLocal = None
        database.init_db()

        from fastapi.testclient import TestClient
        from main import app
        from services.email_service import clear_captured_emails

        clear_captured_emails()
        cls.client = TestClient(app)
        cls.Session = database.get_session_factory()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        import db.database as database

        database._engine = None
        database._SessionLocal = None
        cls._tmpdir.cleanup()

    def test_signup_does_not_authenticate_until_verify(self) -> None:
        from db.models import EmailMessage, User, UserSession
        from services.email_service import captured_emails, clear_captured_emails

        clear_captured_emails()
        r = self.client.post(
            "/api/auth/register",
            json={
                "email": "welcome@visiondock.test",
                "password": "SecurePass1!",
                "name": "Welcome User",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertFalse(body["authenticated"])
        self.assertTrue(body.get("requires_email_verification"))
        self.assertTrue(body.get("email_sent"))
        self.assertIn("Confirm the link", body.get("message", ""))

        me = self.client.get("/api/auth/me")
        self.assertFalse(me.json().get("authenticated"))

        login = self.client.post(
            "/api/auth/login",
            json={"username": "welcome@visiondock.test", "password": "SecurePass1!"},
        )
        self.assertEqual(login.status_code, 403, login.text)
        self.assertEqual(login.json()["detail"]["code"], "email_unverified")

        captured = captured_emails()
        self.assertEqual(len(captured), 1)
        match = re.search(r"token=([^\s]+)", captured[0]["text"])
        self.assertIsNotNone(match)
        token = match.group(1)

        vr = self.client.get(f"/api/auth/verify-email?token={token}", follow_redirects=False)
        self.assertIn(vr.status_code, (302, 307))
        self.assertIn("email_verified=1", vr.headers.get("location", ""))

        me2 = self.client.get("/api/auth/me")
        self.assertTrue(me2.json().get("authenticated"))
        self.assertTrue(me2.json().get("email_verified"))

        db = self.Session()
        try:
            user = db.query(User).filter(User.email == "welcome@visiondock.test").one()
            self.assertIsNotNone(user.email_verified_at)
            sessions = db.query(UserSession).filter(UserSession.user_id == user.id).all()
            self.assertGreaterEqual(len(sessions), 1)
            mails = db.query(EmailMessage).filter(EmailMessage.user_id == user.id).all()
            self.assertEqual(len(mails), 1)
        finally:
            db.close()

    def test_signin_mints_new_db_session(self) -> None:
        from db.models import UserSession
        from services.email_service import captured_emails, clear_captured_emails

        email = "signin.flow@visiondock.test"
        clear_captured_emails()
        self.client.post(
            "/api/auth/register",
            json={"email": email, "password": "SecurePass1!"},
        )
        token = re.search(r"token=([^\s]+)", captured_emails()[-1]["text"]).group(1)
        self.client.get(f"/api/auth/verify-email?token={token}", follow_redirects=False)
        first = self.client.get("/api/auth/me").json()["session_id"]
        self.client.post("/api/auth/logout")
        r = self.client.post(
            "/api/auth/login",
            json={"username": email, "password": "SecurePass1!"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        second = r.json()["session_id"]
        self.assertNotEqual(first, second)

        db = self.Session()
        try:
            rows = (
                db.query(UserSession)
                .filter(UserSession.user_id == r.json()["user_id"])
                .order_by(UserSession.id.asc())
                .all()
            )
            self.assertGreaterEqual(len(rows), 2)
            revoked = [x for x in rows if x.id == first][0]
            self.assertIsNotNone(revoked.revoked_at)
            active = [x for x in rows if x.id == second][0]
            self.assertIsNone(active.revoked_at)
        finally:
            db.close()

    def test_revoke_session_blocks_api(self) -> None:
        from services.email_service import captured_emails, clear_captured_emails

        email = "revoke.me@visiondock.test"
        clear_captured_emails()
        self.client.post(
            "/api/auth/register",
            json={"email": email, "password": "SecurePass1!"},
        )
        token = re.search(r"token=([^\s]+)", captured_emails()[-1]["text"]).group(1)
        self.client.get(f"/api/auth/verify-email?token={token}", follow_redirects=False)
        sid = self.client.get("/api/auth/me").json()["session_id"]
        revoked = self.client.delete(f"/api/auth/sessions/{sid}")
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertTrue(revoked.json().get("logged_out"))
        me = self.client.get("/api/auth/me")
        self.assertFalse(me.json().get("authenticated"))

    def test_config_flags(self) -> None:
        cfg = self.client.get("/api/auth/config")
        self.assertEqual(cfg.status_code, 200)
        data = cfg.json()
        self.assertTrue(data["signup"])
        self.assertTrue(data["password"])
        self.assertTrue(data["email_verify_required"])
        self.assertIn("email_delivery", data)


if __name__ == "__main__":
    unittest.main()
