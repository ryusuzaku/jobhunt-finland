"""Focused tests for the isolated hosted backend.

These tests do not import the legacy app, launch a server, contact Manus, or use
managed MySQL. PyJWT is intentionally used to sign the same HS256-shaped test
sessions validated in production.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import jwt
except ImportError:  # Parent owns dependency installation; preserve unit-test discovery meanwhile.
    jwt = None

from fastapi.testclient import TestClient

from src.hosted.app import create_app
from src.hosted.auth import AuthSettings, SESSION_COOKIE
from src.hosted.models import HostedJob, create_schema


@unittest.skipIf(jwt is None, "PyJWT must be installed by hosted deployment dependencies")
class HostedBackendTests(unittest.TestCase):
    project_id = "project-under-test"
    signing_secret = "hosted-test-signing-secret-with-at-least-thirty-two-bytes"

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database_url = f"sqlite:///{Path(self.tempdir.name) / 'hosted-test.db'}"
        self.app = create_app(
            database_url=database_url,
            auth_settings=AuthSettings(
                project_id=self.project_id,
                jwt_secret=self.signing_secret,
                oauth_portal_url="https://oauth.example.invalid",
                oauth_api_url="https://oauth-api.example.invalid",
                cookie_secure=False,
            ),
        )
        create_schema(self.app.state.engine)

    def tearDown(self):
        self.app.state.engine.dispose()
        self.tempdir.cleanup()

    def signed_session(self, open_id: str, *, app_id: str | None = None) -> str:
        return jwt.encode(
            {
                "appId": app_id or self.project_id,
                "openId": open_id,
                "name": f"{open_id} name",
                "email": f"{open_id}@example.test",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
            },
            self.signing_secret,
            algorithm="HS256",
        )

    def signed_client(self, open_id: str) -> tuple[TestClient, str]:
        client = TestClient(self.app)
        client.cookies.set(SESSION_COOKIE, self.signed_session(open_id))
        response = client.get("/api/profile")
        self.assertEqual(response.status_code, 200, response.text)
        return client, response.json()["csrf_token"]

    def add_job(self, source_id: str, title: str, description: str = "", location: str = "Helsinki") -> int:
        with self.app.state.session_factory() as db:
            job = HostedJob(
                source="unit",
                source_id=source_id,
                title=title,
                company="Unit Co",
                location=location,
                description=description,
                url="https://example.test/jobs/" + source_id,
                remote=False,
                hybrid=False,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job.id

    def test_authentication_requires_a_real_project_signed_session(self):
        anonymous = TestClient(self.app)
        response = anonymous.get("/api/profile")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Authentication required", response.json()["detail"])

        wrong_project = TestClient(self.app)
        wrong_project.cookies.set(SESSION_COOKIE, self.signed_session("alice", app_id="another-project"))
        response = wrong_project.get("/api/profile")
        self.assertEqual(response.status_code, 401)
        self.assertIn("different project", response.json()["detail"])

    def test_csrf_profile_revision_and_profile_completion_rules(self):
        client, csrf = self.signed_client("alice")
        profile = client.get("/api/profile").json()
        job_id = self.add_job("csrf-job", "Python developer", "Python work")

        no_csrf = client.post(f"/api/jobs/{job_id}/save", json={"saved": True})
        self.assertEqual(no_csrf.status_code, 403)

        first_save = client.post(
            "/api/profile",
            headers={"X-CSRF-Token": csrf},
            json={"revision": profile["revision"], "preferred_tech": ["python"]},
        )
        self.assertEqual(first_save.status_code, 200, first_save.text)
        next_revision = first_save.json()["profile"]["revision"]

        stale_save = client.post(
            "/api/profile",
            headers={"X-CSRF-Token": csrf},
            json={"revision": profile["revision"], "preferred_tech": ["go"]},
        )
        self.assertEqual(stale_save.status_code, 409)

        cannot_complete_without_review = client.post(
            "/api/profile/complete",
            headers={"X-CSRF-Token": csrf},
            json={"revision": next_revision},
        )
        self.assertEqual(cannot_complete_without_review.status_code, 400)

        draft = client.post(
            "/api/profile/draft",
            headers={"X-CSRF-Token": csrf},
            json={"step": 6, "job_profiles": ["software"]},
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        completed = client.post(
            "/api/profile/complete",
            headers={"X-CSRF-Token": csrf},
            json={"revision": draft.json()["profile"]["revision"]},
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertTrue(completed.json()["profile"]["onboarding_completed"])

        saved = client.post(
            f"/api/jobs/{job_id}/save",
            headers={"X-CSRF-Token": csrf},
            json={"saved": True},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["saved"])

    def test_saved_and_tracker_records_are_owned_by_the_authenticated_user(self):
        job_id = self.add_job("owned-job", "Backend developer", "Python API work")
        alice, alice_csrf = self.signed_client("alice")
        bob, bob_csrf = self.signed_client("bob")

        self.assertEqual(
            alice.post(
                f"/api/jobs/{job_id}/save",
                headers={"X-CSRF-Token": alice_csrf},
                json={"saved": True},
            ).status_code,
            200,
        )
        application = alice.post(
            f"/api/jobs/{job_id}/application",
            headers={"X-CSRF-Token": alice_csrf},
            json={"status": "applied", "notes": "Sent application", "outcome": None},
        )
        self.assertEqual(application.status_code, 200, application.text)
        application_id = application.json()["application"]["id"]

        bob_jobs = bob.get("/api/jobs?show_applied=true")
        self.assertEqual(bob_jobs.status_code, 200)
        presented = bob_jobs.json()["jobs"]
        self.assertEqual(len(presented), 1)
        self.assertFalse(presented[0]["saved"])
        self.assertIsNone(presented[0]["application"])

        forbidden_delete = bob.delete(
            f"/api/applications/{application_id}", headers={"X-CSRF-Token": bob_csrf}
        )
        self.assertEqual(forbidden_delete.status_code, 404)
        self.assertEqual(alice.get("/api/jobs?show_applied=true").json()["jobs"][0]["application"]["status"], "applied")

    def test_personalized_ranking_happens_before_pagination_and_min_score(self):
        client, csrf = self.signed_client("ranker")
        profile = client.get("/api/profile").json()
        saved_profile = client.post(
            "/api/profile",
            headers={"X-CSRF-Token": csrf},
            json={
                "revision": profile["revision"],
                "job_profiles": ["software"],
                "preferred_tech": ["python"],
                "preferred_locations": ["helsinki"],
            },
        )
        self.assertEqual(saved_profile.status_code, 200, saved_profile.text)

        for index in range(24):
            self.add_job(f"low-{index}", f"Software developer {index}", "General development tasks", "Helsinki")
        best_id = self.add_job("best", "Python software developer", "Python API and mentoring", "Helsinki")

        first_page = client.get("/api/jobs?page=1&sort=match")
        self.assertEqual(first_page.status_code, 200)
        payload = first_page.json()
        self.assertEqual(payload["total"], 25)
        self.assertEqual(payload["page_count"], 2)
        self.assertEqual(payload["jobs"][0]["id"], best_id)

        highest = payload["jobs"][0]["score"]
        lowest = payload["jobs"][-1]["score"]
        self.assertGreater(highest, lowest)
        thresholded = client.get(f"/api/jobs?min_score={(highest + lowest) / 2}")
        self.assertEqual(thresholded.status_code, 200)
        self.assertEqual(thresholded.json()["total"], 1)
        self.assertEqual(thresholded.json()["jobs"][0]["id"], best_id)

    def test_scheduled_callback_rejects_an_ordinary_or_missing_cron_session(self):
        client = TestClient(self.app)
        missing = client.post("/api/scheduled/refresh")
        self.assertEqual(missing.status_code, 401)

        client.cookies.set(SESSION_COOKIE, self.signed_session("ordinary-user"))
        ordinary = client.post("/api/scheduled/refresh")
        self.assertEqual(ordinary.status_code, 401)
        self.assertIn("Scheduled callback", ordinary.json()["error"])


if __name__ == "__main__":
    unittest.main()
