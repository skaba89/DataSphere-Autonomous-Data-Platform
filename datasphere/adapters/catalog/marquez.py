from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("catalog", "marquez")
class MarquezAdapter(BaseAdapter):
    name = "marquez"
    category = "catalog"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 5000}/api/v1/namespaces"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("marquez: host is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 5000
        return f"""  marquez:
    image: marquezproject/marquez:0.47.0
    ports:
      - "{port}:5000"
      - "5001:5001"
    environment:
      MARQUEZ_PORT: 5000
      MARQUEZ_ADMIN_PORT: 5001
      DATABASE_HOST: postgresql
      DATABASE_PORT: 5432
      DATABASE_DB: marquez
      DATABASE_USER: marquez
      DATABASE_PASSWORD: ${{MARQUEZ_DB_PASSWORD}}
    depends_on:
      - postgresql

  marquez-web:
    image: marquezproject/marquez-web:0.47.0
    ports:
      - "3000:3000"
    environment:
      MARQUEZ_HOST: marquez
      MARQUEZ_PORT: 5000
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
