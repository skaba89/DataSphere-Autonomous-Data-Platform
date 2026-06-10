from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("catalog", "amundsen")
class AmundsenAdapter(BaseAdapter):
    name = "amundsen"
    category = "catalog"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 5000}/healthcheck"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("amundsen: host is required")
        return errors

    def deploy(self) -> str:
        return f"""  amundsen-frontend:
    image: amundsendev/amundsen-frontend:4.2.0
    ports:
      - "{self.config.port or 5000}:5000"
    environment:
      SEARCHSERVICE_BASE: http://amundsen-search:5001
      METADATASERVICE_BASE: http://amundsen-metadata:5002

  amundsen-search:
    image: amundsendev/amundsen-search:4.0.0
    ports:
      - "5001:5001"
    environment:
      ELASTICSEARCH_ENDPOINT: http://elasticsearch:9200

  amundsen-metadata:
    image: amundsendev/amundsen-metadata:3.14.0
    ports:
      - "5002:5002"
    environment:
      PROXY_HOST: bolt://neo4j:7687
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
