"""Tests for Slack and Microsoft Teams notification sender."""
from __future__ import annotations
import json
import time
import unittest
from unittest.mock import patch, MagicMock

from datasphere.api.notifications import send_slack, send_teams, NotificationService


def _mock_urlopen_200():
    """Return a context-manager mock whose .status == 200."""
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# send_slack tests
# ---------------------------------------------------------------------------

class TestSendSlack(unittest.TestCase):
    def test_send_slack_success(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_200()):
            result = send_slack("https://hooks.slack.com/test", "job-abc", "completed")
        self.assertTrue(result)

    def test_send_slack_failure(self):
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = send_slack("https://hooks.slack.com/test", "job-abc", "completed")
        self.assertFalse(result)

    def test_send_slack_payload_has_job_id(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_slack("https://hooks.slack.com/test", "abcdef1234567890", "completed")

        body = captured["body"]
        text = json.dumps(body)
        self.assertIn("abcdef12", text)

    def test_send_slack_payload_has_status_completed(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_slack("https://hooks.slack.com/test", "job-xyz", "completed")

        text = json.dumps(captured["body"])
        self.assertIn("completed", text.lower())

    def test_send_slack_payload_has_status_failed(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_slack("https://hooks.slack.com/test", "job-xyz", "failed")

        text = json.dumps(captured["body"])
        self.assertIn("failed", text.lower())

    def test_send_slack_includes_cost_when_present(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        result_data = {"cost_optimization": {"total_monthly_usd": 1500}}
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_slack("https://hooks.slack.com/test", "job-xyz", "completed", result=result_data)

        text = json.dumps(captured["body"])
        self.assertIn("1,500", text)

    def test_send_slack_includes_stack_when_present(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        result_data = {"stack_advisor": {"validated_stack": {"warehouse": "snowflake", "orchestrator": "airflow"}}}
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_slack("https://hooks.slack.com/test", "job-xyz", "completed", result=result_data)

        text = json.dumps(captured["body"])
        self.assertIn("snowflake", text)
        self.assertIn("airflow", text)


# ---------------------------------------------------------------------------
# send_teams tests
# ---------------------------------------------------------------------------

class TestSendTeams(unittest.TestCase):
    def test_send_teams_success(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_200()):
            result = send_teams("https://outlook.office.com/webhook/test", "job-abc", "completed")
        self.assertTrue(result)

    def test_send_teams_payload_has_theme_color_green_on_completed(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_teams("https://outlook.office.com/webhook/test", "job-abc", "completed")

        self.assertEqual(captured["body"]["themeColor"], "22c55e")

    def test_send_teams_payload_has_theme_color_red_on_failed(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_teams("https://outlook.office.com/webhook/test", "job-abc", "failed")

        self.assertEqual(captured["body"]["themeColor"], "ef4444")

    def test_send_teams_facts_include_job_id(self):
        captured = {}
        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _mock_urlopen_200()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            send_teams("https://outlook.office.com/webhook/test", "abcdef1234567890", "completed")

        facts = captured["body"]["sections"][0]["facts"]
        fact_values = {f["name"]: f["value"] for f in facts}
        self.assertIn("Job ID", fact_values)
        self.assertIn("abcdef12", fact_values["Job ID"])


# ---------------------------------------------------------------------------
# NotificationService tests
# ---------------------------------------------------------------------------

class TestNotificationService(unittest.TestCase):
    def test_notification_service_no_urls_does_nothing(self):
        """No env vars, no URLs → no HTTP calls made."""
        svc = NotificationService()
        env_patch = {"DATASPHERE_SLACK_WEBHOOK_URL": "", "DATASPHERE_TEAMS_WEBHOOK_URL": ""}
        with patch.dict("os.environ", env_patch, clear=False):
            with patch("urllib.request.urlopen") as mock_open:
                svc.notify_async(job_id="job-001", status="completed")
                # Give threads a moment to run (there shouldn't be any)
                time.sleep(0.05)
                mock_open.assert_not_called()

    def test_notification_service_uses_env_slack(self):
        """DATASPHERE_SLACK_WEBHOOK_URL set → Slack endpoint called."""
        svc = NotificationService()
        env_patch = {
            "DATASPHERE_SLACK_WEBHOOK_URL": "https://hooks.slack.com/env-test",
            "DATASPHERE_TEAMS_WEBHOOK_URL": "",
        }
        called_urls = []
        def fake_urlopen(req, timeout=None):
            called_urls.append(req.full_url)
            return _mock_urlopen_200()

        with patch.dict("os.environ", env_patch, clear=False):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                svc.notify_async(job_id="job-002", status="completed")
                # Wait for daemon thread
                time.sleep(0.2)

        self.assertTrue(any("hooks.slack.com" in u for u in called_urls))

    def test_notification_service_uses_env_teams(self):
        """DATASPHERE_TEAMS_WEBHOOK_URL set → Teams endpoint called."""
        svc = NotificationService()
        env_patch = {
            "DATASPHERE_SLACK_WEBHOOK_URL": "",
            "DATASPHERE_TEAMS_WEBHOOK_URL": "https://outlook.office.com/webhook/env-test",
        }
        called_urls = []
        def fake_urlopen(req, timeout=None):
            called_urls.append(req.full_url)
            return _mock_urlopen_200()

        with patch.dict("os.environ", env_patch, clear=False):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                svc.notify_async(job_id="job-003", status="failed")
                time.sleep(0.2)

        self.assertTrue(any("outlook.office.com" in u for u in called_urls))

    def test_notification_service_notify_async_is_nonblocking(self):
        """notify_async should return quickly even if HTTP is slow."""
        svc = NotificationService()

        def slow_urlopen(req, timeout=None):
            time.sleep(5)  # simulate very slow network
            return _mock_urlopen_200()

        start = time.time()
        with patch("urllib.request.urlopen", side_effect=slow_urlopen):
            svc.notify_async(
                job_id="job-004",
                status="completed",
                slack_url="https://hooks.slack.com/slow-test",
            )
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0, f"notify_async blocked for {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
