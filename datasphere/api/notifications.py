"""
Slack and Microsoft Teams notification sender for DataSphere API.

Activated per-tenant via:
- DATASPHERE_SLACK_WEBHOOK_URL  (global default)
- X-Slack-Webhook header (per-request override)
- DATASPHERE_TEAMS_WEBHOOK_URL  (global default)
- X-Teams-Webhook header (per-request override)
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error
from typing import Any

_log = logging.getLogger(__name__)
_TIMEOUT = 10


def _post_json(url: str, payload: dict) -> bool:
    """POST JSON to a webhook URL. Returns True on success."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "DataSphere/1.2"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        _log.warning("notification_send_failed url=%s error=%s", url[:40], exc)
        return False


def send_slack(
    webhook_url: str,
    job_id: str,
    status: str,
    result: dict | None = None,
    duration_s: float = 0.0,
    tenant_id: str = "default",
) -> bool:
    """Send a Slack Block Kit notification."""
    color = "#22c55e" if status == "completed" else "#ef4444"
    icon = "✅" if status == "completed" else "❌"

    stack = {}
    cost = 0
    if result:
        sa = result.get("stack_advisor", {})
        stack = sa.get("validated_stack", {})
        co = result.get("cost_optimization", {})
        cost = co.get("total_monthly_usd", 0)

    stack_text = " · ".join(f"{k}: {v}" for k, v in list(stack.items())[:4]) if stack else "—"

    payload = {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"{icon} DataSphere Job {status.title()}"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Job ID*\n`{job_id[:8]}…`"},
                            {"type": "mrkdwn", "text": f"*Status*\n{status}"},
                            {"type": "mrkdwn", "text": f"*Duration*\n{duration_s:.1f}s"},
                            {"type": "mrkdwn", "text": f"*Cost*\n${cost:,}/mo" if cost else "*Cost*\n—"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Stack*\n{stack_text}"},
                    },
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": f"Tenant: {tenant_id}"}],
                    },
                ],
            }
        ]
    }
    return _post_json(webhook_url, payload)


def send_teams(
    webhook_url: str,
    job_id: str,
    status: str,
    result: dict | None = None,
    duration_s: float = 0.0,
    tenant_id: str = "default",
) -> bool:
    """Send a Microsoft Teams Adaptive Card notification."""
    color = "good" if status == "completed" else "attention"
    icon = "✅" if status == "completed" else "❌"

    stack = {}
    cost = 0
    if result:
        sa = result.get("stack_advisor", {})
        stack = sa.get("validated_stack", {})
        co = result.get("cost_optimization", {})
        cost = co.get("total_monthly_usd", 0)

    facts = [
        {"name": "Job ID", "value": f"`{job_id[:8]}…`"},
        {"name": "Status", "value": status},
        {"name": "Duration", "value": f"{duration_s:.1f}s"},
        {"name": "Tenant", "value": tenant_id},
    ]
    if cost:
        facts.append({"name": "Estimated Cost", "value": f"${cost:,}/month"})
    for k, v in list(stack.items())[:3]:
        facts.append({"name": k.replace("_", " ").title(), "value": str(v)})

    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "22c55e" if status == "completed" else "ef4444",
        "summary": f"DataSphere Job {status}",
        "sections": [
            {
                "activityTitle": f"{icon} DataSphere Job {status.title()}",
                "activitySubtitle": f"Job `{job_id[:8]}` {status}",
                "facts": facts,
            }
        ],
    }
    return _post_json(webhook_url, payload)


class NotificationService:
    """Send job notifications to Slack and/or Teams."""

    def notify_async(
        self,
        job_id: str,
        status: str,
        result: dict | None = None,
        duration_s: float = 0.0,
        tenant_id: str = "default",
        slack_url: str = "",
        teams_url: str = "",
    ) -> None:
        """Fire notifications in background threads."""
        # Fall back to environment variables
        slack_url = slack_url or os.environ.get("DATASPHERE_SLACK_WEBHOOK_URL", "")
        teams_url = teams_url or os.environ.get("DATASPHERE_TEAMS_WEBHOOK_URL", "")

        if slack_url:
            t = threading.Thread(
                target=send_slack,
                args=(slack_url, job_id, status, result, duration_s, tenant_id),
                daemon=True,
            )
            t.start()

        if teams_url:
            t = threading.Thread(
                target=send_teams,
                args=(teams_url, job_id, status, result, duration_s, tenant_id),
                daemon=True,
            )
            t.start()


notification_service = NotificationService()
