from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("bi", "redash")
class RedashAdapter(BaseAdapter):
    name = "redash"
    category = "bi"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 5000}/api/queries"
        req = urllib.request.Request(url, headers={"Authorization": f"Key {self.config.password or ''}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("redash: host is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 5000
        return f"""  redash:
    image: redash/redash:10.1.0.b50633
    command: server
    ports:
      - "{port}:5000"
    environment:
      REDASH_DATABASE_URL: postgresql://redash:${{REDASH_DB_PASSWORD}}@postgresql/redash
      REDASH_REDIS_URL: redis://redis:6379/0
      REDASH_SECRET_KEY: ${{REDASH_SECRET_KEY}}
    depends_on:
      - postgresql
      - redis

  redash-worker:
    image: redash/redash:10.1.0.b50633
    command: worker
    environment:
      REDASH_DATABASE_URL: postgresql://redash:${{REDASH_DB_PASSWORD}}@postgresql/redash
      REDASH_REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgresql
      - redis
"""

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
