from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("monitoring", "grafana")
class GrafanaAdapter(BaseAdapter):
    name = "grafana"
    category = "monitoring"

    def connect(self):
        import requests
        session = requests.Session()
        session.auth = (self.config.username or "admin", self.config.password or "admin")
        return session

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  grafana:
    image: grafana/grafana:latest
    ports:
      - "{self.config.port or 3000}:3000"
    environment:
      GF_SECURITY_ADMIN_USER: ${{GRAFANA_USER:-admin}}
      GF_SECURITY_ADMIN_PASSWORD: ${{GRAFANA_PASSWORD}}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./infra/grafana/provisioning:/etc/grafana/provisioning
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
