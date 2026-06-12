"""
Simple Bearer-token authentication for the DataSphere API.

Token is read from the environment variable DATASPHERE_API_KEY.
If the variable is not set, auth is disabled (dev mode).
"""
from __future__ import annotations
import os
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def _expected_key() -> str | None:
    return os.environ.get("DATASPHERE_API_KEY") or None


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    """FastAPI dependency — raises 401 if auth is enabled and token is wrong."""
    key = _expected_key()
    if key is None:
        return  # auth disabled
    if credentials is None or credentials.credentials != key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def auth_status() -> dict:
    """Returns whether auth is enabled and a hint for the UI."""
    enabled = _expected_key() is not None
    return {
        "auth_enabled": enabled,
        "hint": "Set DATASPHERE_API_KEY env var to enable auth" if not enabled else "Bearer token required",
    }
