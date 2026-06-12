from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("monitoring", "prometheus")
class PrometheusAdapter(BaseAdapter):
    name = "prometheus"
    category = "monitoring"

    def connect(self):
        import requests
        return requests.Session()

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  prometheus:
    image: prom/prometheus:latest
    ports:
      - "{self.config.port or 9090}:9090"
    volumes:
      - ./infra/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'
"""

    def status(self):
        try:
            import requests
            r = requests.get(f"http://{self.config.host or 'localhost'}:{self.config.port or 9090}/-/healthy", timeout=3)
            return {"adapter": self.name, "status": "healthy" if r.status_code == 200 else "degraded"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
