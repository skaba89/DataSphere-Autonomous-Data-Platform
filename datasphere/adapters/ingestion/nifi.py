from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("ingestion", "nifi")
class NiFiAdapter(BaseAdapter):
    name = "nifi"
    category = "ingestion"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 8080}/nifi-api/system-diagnostics"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("nifi: host is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 8080
        return f"""  nifi:
    image: apache/nifi:1.26.0
    ports:
      - "{port}:8080"
    environment:
      NIFI_WEB_HTTP_PORT: "8080"
      SINGLE_USER_CREDENTIALS_USERNAME: admin
      SINGLE_USER_CREDENTIALS_PASSWORD: ${{NIFI_PASSWORD}}
    volumes:
      - nifi_data:/opt/nifi/nifi-current/data
      - nifi_logs:/opt/nifi/nifi-current/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/nifi-api/system-diagnostics"]
      interval: 30s
      timeout: 10s
      retries: 5
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
