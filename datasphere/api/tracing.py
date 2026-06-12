"""
Optional OpenTelemetry tracing for DataSphere API.

Activated when DATASPHERE_OTLP_ENDPOINT env var is set.
Falls back to no-op if opentelemetry-sdk is not installed.
"""
from __future__ import annotations
import os
import logging

_log = logging.getLogger(__name__)
_tracer = None
_enabled = False


def setup_tracing(service_name: str = "datasphere-api") -> None:
    """Initialize OTel tracing if SDK available and endpoint configured."""
    global _tracer, _enabled
    endpoint = os.environ.get("DATASPHERE_OTLP_ENDPOINT", "")
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name, "service.version": "1.2.0"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        _enabled = True
        _log.info("otel_tracing_enabled endpoint=%s", endpoint)
    except ImportError:
        _log.debug("opentelemetry-sdk not installed — tracing disabled")
    except Exception as exc:
        _log.warning("otel_tracing_setup_failed error=%s", exc)


def get_tracer():
    """Return tracer or None if disabled."""
    return _tracer


def is_enabled() -> bool:
    return _enabled


class _NoopSpan:
    """No-op context manager for when tracing is disabled."""
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def set_attribute(self, *_): pass
    def record_exception(self, *_): pass
    def set_status(self, *_): pass


def start_span(name: str, attributes: dict | None = None):
    """Start a span or return a no-op if tracing is disabled."""
    if _tracer is None:
        return _NoopSpan()
    span = _tracer.start_as_current_span(name)
    return span
