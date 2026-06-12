"""
Structured JSON logging for DataSphere API.

Usage:
    from datasphere.api.logging_config import setup_logging, get_logger
    setup_logging()
    logger = get_logger(__name__)
    logger.info("job started", job_id=job_id, mode=mode)
"""
from __future__ import annotations
import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

# Context variable — propagated across async/sync boundaries
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def _get_tenant_id_safe() -> str:
    try:
        from datasphere.api.tenancy import get_tenant_id
        return get_tenant_id()
    except Exception:
        return ""


def _get_trace_id() -> str:
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            return format(ctx.trace_id, '032x')
    except Exception:
        pass
    return ""

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.environ.get("LOG_FORMAT", "json")  # "json" | "text"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":        self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
            "request_id": _request_id_var.get(""),
            "tenant_id":  _get_tenant_id_safe(),
            "trace_id": _get_trace_id(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Extra fields passed via logger.info("msg", extra={"key": val})
        for k, v in record.__dict__.items():
            if k not in logging.LogRecord.__dict__ and not k.startswith("_"):
                payload[k] = v
        return json.dumps(payload, default=str)


class _TextFormatter(logging.Formatter):
    FMT = "%(asctime)s [%(levelname)s] %(name)s %(message)s"
    DATE = "%H:%M:%S"

    def __init__(self):
        super().__init__(fmt=self.FMT, datefmt=self.DATE)


def setup_logging() -> None:
    """Configure root logger. Call once at application startup."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _JsonFormatter() if LOG_FORMAT == "json" else _TextFormatter()
    )
    root.addHandler(handler)
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def get_request_id() -> str:
    return _request_id_var.get("") or str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)
