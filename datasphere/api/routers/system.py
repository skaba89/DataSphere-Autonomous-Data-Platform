"""System routes: health, readyz, metrics, plugins, ui, root."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from datasphere.api.auth import auth_status
from datasphere.api.job_store import job_store
from datasphere.api.metrics import metrics
from datasphere.api.artifact_store import artifact_store
from datasphere.plugins import plugin_registry

_VERSION = "1.2.0"
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

router = APIRouter(tags=["system"])


@router.get("/health", tags=["system"])
@router.get("/healthz", tags=["system"])
def health() -> dict:
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok", "version": _VERSION, "timestamp": time.time(), **auth_status()}


@router.get("/readyz", tags=["system"])
def readyz() -> dict:
    """Readiness probe — returns 503 if dependencies are unavailable."""
    checks: dict[str, str] = {}
    ok = True

    try:
        job_store.list_all()
        checks["job_store"] = "ok"
    except Exception as exc:
        checks["job_store"] = f"error: {exc}"
        ok = False

    try:
        with tempfile.NamedTemporaryFile(prefix="datasphere_ready_", delete=True):
            pass
        checks["tmp_dir"] = "ok"
    except Exception as exc:
        checks["tmp_dir"] = f"error: {exc}"
        ok = False

    try:
        artifact_store.list_files("__health_check__")
        checks["artifact_store"] = "ok"
    except Exception as exc:
        checks["artifact_store"] = f"error: {exc}"
        ok = False

    status_code = 200 if ok else 503
    return JSONResponse(
        content={"status": "ready" if ok else "not_ready", "checks": checks, "version": _VERSION},
        status_code=status_code,
    )


@router.get("/metrics", tags=["system"], response_class=PlainTextResponse)
def prometheus_metrics() -> PlainTextResponse:
    """
    Prometheus-compatible metrics endpoint.

    Metrics: http_requests_total, http_request_duration_seconds,
    jobs_created_total, jobs_completed_total, jobs_failed_total,
    generation_duration_seconds, uptime_seconds.
    """
    return PlainTextResponse(
        content=metrics.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/plugins", tags=["system"])
def list_plugins() -> dict:
    """List all available generator plugins (built-in + installed)."""
    plugin_registry.load()
    plugins = plugin_registry.list_all()
    return {
        "count": len(plugins),
        "plugins": [p.to_dict() for p in plugins],
        "builtin_count": sum(1 for p in plugins if p.source == "builtin"),
        "external_count": sum(1 for p in plugins if p.source == "plugin"),
    }


@router.get("/ui", response_class=HTMLResponse, tags=["ui"], include_in_schema=False)
@router.get("/ui/", response_class=HTMLResponse, tags=["ui"], include_in_schema=False)
def web_ui() -> HTMLResponse:
    """Interface web DataSphere."""
    html_file = _TEMPLATE_DIR / "index.html"
    if not html_file.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


@router.get("/", tags=["system"])
def root() -> dict:
    return {
        "name": "DataSphere Autonomous Data Platform",
        "version": _VERSION,
        "api_versions": {
            "v1": "/v1",
            "current": "v1",
            "deprecated": ["unversioned (no /v1 prefix)"],
        },
        "ui":   "/ui",
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "GET  /ui  → Interface web",
            "POST /v1/generate",
            "GET  /v1/generate/stream?job_id=<id>",
            "GET  /v1/healthz  /v1/readyz",
            "GET  /v1/jobs/{job_id}",
            "POST /v1/proposals",
            "POST /v1/dbt/generate",
            "POST /v1/dags/airflow/generate",
            "POST /v1/dagster/generate",
            "POST /v1/prefect/generate",
            "POST /v1/terraform/generate",
            "GET  /v1/stacks/supported",
            "Multi-tenant: set X-Tenant-ID header to isolate jobs per tenant",
            "GET  /v1/metrics  → Prometheus metrics",
            "GET  /v1/plugins",
            "NOTE: Unversioned routes (without /v1) are deprecated and return Deprecation: true header",
        ],
    }
