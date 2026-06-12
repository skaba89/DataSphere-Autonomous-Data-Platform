from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("orchestration", "kestra")
class KestraAdapter(BaseAdapter):
    name = "kestra"
    category = "orchestration"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 8080}/api/v1/flows"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("kestra: host is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 8080
        return f"""  kestra:
    image: kestra/kestra:latest
    command: server standalone --worker-thread=128
    environment:
      KESTRA_CONFIGURATION: |
        datasources:
          postgres:
            url: jdbc:postgresql://postgresql:5432/kestra
            username: kestra
            password: ${{KESTRA_DB_PASSWORD}}
    ports:
      - "{port}:{port}"
    depends_on:
      - postgresql
    volumes:
      - kestra_data:/app/storage
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
