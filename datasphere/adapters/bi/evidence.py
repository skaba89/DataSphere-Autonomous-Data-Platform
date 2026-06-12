from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("bi", "evidence")
class EvidenceAdapter(BaseAdapter):
    name = "evidence"
    category = "bi"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 3000}"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        port = self.config.port or 3000
        return f"""  evidence:
    image: ghcr.io/evidence-dev/evidence:latest
    ports:
      - "{port}:3000"
    environment:
      DATABASE: postgresql
      POSTGRES_HOST: postgresql
      POSTGRES_USER: {self.config.username or "datasphere"}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD}}
      POSTGRES_DATABASE: {self.config.database or "datasphere"}
    volumes:
      - ./evidence:/app/pages/reports
    depends_on:
      - postgresql
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
