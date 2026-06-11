"""
Multi-tenant support for DataSphere API.

Tenants are identified by X-Tenant-ID header.
If not set, defaults to "default" tenant.
"""
from __future__ import annotations
import re
from contextvars import ContextVar
from typing import Optional

_TENANT_ID_VAR: ContextVar[str] = ContextVar("tenant_id", default="default")
_TENANT_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$')


def validate_tenant_id(tenant_id: str) -> bool:
    """Return True if tenant_id is valid."""
    return bool(_TENANT_PATTERN.match(tenant_id))


def get_tenant_id() -> str:
    return _TENANT_ID_VAR.get()


def set_tenant_id(tenant_id: str) -> None:
    _TENANT_ID_VAR.set(tenant_id)


def tenant_job_id(job_id: str) -> str:
    """Prefix job_id with tenant for storage isolation."""
    tenant = get_tenant_id()
    if tenant == "default":
        return job_id
    return f"{tenant}:{job_id}"


def extract_raw_job_id(scoped_job_id: str) -> str:
    """Strip tenant prefix from job_id."""
    if ":" in scoped_job_id:
        return scoped_job_id.split(":", 1)[1]
    return scoped_job_id
