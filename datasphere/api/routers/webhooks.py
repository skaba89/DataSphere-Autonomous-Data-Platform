"""Webhook routes: register, list, deliveries, delete."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from datasphere.api.auth import require_auth
from datasphere.api.tenancy import get_tenant_id
from datasphere.api.webhooks import webhook_registry
from datasphere.api.models import WebhookRegisterRequest
from datasphere.api.openapi_examples import WEBHOOK_REQUEST_EXAMPLE

router = APIRouter(tags=["webhooks"])


@router.post(
    "/webhooks",
    tags=["webhooks"],
    summary="Enregistrer un webhook",
    description="""
Enregistre une URL webhook pour recevoir des notifications HTTP sur les événements de jobs.

**Événements disponibles:**
- `job.completed` — job terminé avec succès
- `job.failed` — job en erreur
- `*` — tous les événements

**Sécurité HMAC:** Si `secret` est fourni, le payload est signé avec HMAC-SHA256.
Le header `X-DataSphere-Signature` contient la signature à vérifier côté récepteur.

**Isolation multi-tenant:** Les webhooks sont isolés par tenant (`X-Tenant-ID`).
    """,
    response_description="Webhook enregistré avec son identifiant unique",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "all_events": {
                            "summary": "Écouter tous les événements",
                            "value": WEBHOOK_REQUEST_EXAMPLE,
                        },
                        "completed_only": {
                            "summary": "Seulement job.completed",
                            "value": {
                                "url": "https://myapp.example.com/webhooks/datasphere",
                                "events": ["job.completed"],
                            },
                        },
                    }
                }
            }
        },
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "example": {
                            "id": "wh_3fa85f64",
                            "url": "https://hooks.example.com/datasphere",
                            "events": ["job.completed", "job.failed"],
                            "created_at": "2026-06-12T10:00:00Z",
                        }
                    }
                }
            }
        },
    },
)
def register_webhook(req: WebhookRegisterRequest, _: None = Depends(require_auth)) -> dict:
    """Register a webhook URL to be notified on job events."""
    tenant_id = get_tenant_id()
    wh = webhook_registry.register(req.url, tenant_id, req.events, req.secret)
    return {"id": wh.id, "url": wh.url, "events": wh.events, "created_at": wh.created_at}


@router.get("/webhooks", tags=["webhooks"])
def list_webhooks(_: None = Depends(require_auth)) -> list[dict]:
    """List all webhooks for current tenant."""
    tenant_id = get_tenant_id()
    return [{"id": w.id, "url": w.url, "events": w.events, "active": w.active}
            for w in webhook_registry.list_for_tenant(tenant_id)]


@router.get("/webhooks/deliveries", tags=["webhooks"])
def webhook_deliveries(_: None = Depends(require_auth)) -> list[dict]:
    """Recent webhook delivery attempts for current tenant."""
    return webhook_registry.recent_deliveries(get_tenant_id())


@router.delete("/webhooks/{webhook_id}", tags=["webhooks"])
def delete_webhook(webhook_id: str, _: None = Depends(require_auth)) -> dict:
    """Unregister a webhook."""
    tenant_id = get_tenant_id()
    if not webhook_registry.unregister(webhook_id, tenant_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": webhook_id}
