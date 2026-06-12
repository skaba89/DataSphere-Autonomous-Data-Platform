from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("monitoring", "opentelemetry")
class OpenTelemetryAdapter(BaseAdapter):
    name = "opentelemetry"
    category = "monitoring"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 4318}/v1/metrics"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("opentelemetry: collector host is required")
        return errors

    def deploy(self) -> str:
        return f"""  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.102.0
    ports:
      - "4317:4317"   # OTLP gRPC
      - "{self.config.port or 4318}:4318"  # OTLP HTTP
      - "8888:8888"   # Prometheus metrics
    volumes:
      - ./otel-config.yml:/etc/otelcol-contrib/config.yaml
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
