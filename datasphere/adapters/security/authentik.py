from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("security", "authentik")
class AuthentikAdapter(BaseAdapter):
    name = "authentik"
    category = "security"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 9000}/api/v3/core/users/"
        headers = {"Authorization": f"Bearer {self.config.password or ''}"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("authentik: host is required")
        if not self.config.password:
            errors.append("authentik: API token (password) is required")
        return errors

    def deploy(self) -> str:
        port = self.config.port or 9000
        return f"""  authentik-server:
    image: ghcr.io/goauthentik/server:2024.6.0
    command: server
    ports:
      - "{port}:9000"
      - "9443:9443"
    environment:
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_POSTGRESQL__HOST: postgresql
      AUTHENTIK_POSTGRESQL__USER: authentik
      AUTHENTIK_POSTGRESQL__PASSWORD: ${{AUTHENTIK_DB_PASSWORD}}
      AUTHENTIK_POSTGRESQL__NAME: authentik
      AUTHENTIK_SECRET_KEY: ${{AUTHENTIK_SECRET_KEY}}
    depends_on:
      - postgresql
      - redis

  authentik-worker:
    image: ghcr.io/goauthentik/server:2024.6.0
    command: worker
    environment:
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_POSTGRESQL__HOST: postgresql
      AUTHENTIK_POSTGRESQL__USER: authentik
      AUTHENTIK_POSTGRESQL__PASSWORD: ${{AUTHENTIK_DB_PASSWORD}}
      AUTHENTIK_POSTGRESQL__NAME: authentik
      AUTHENTIK_SECRET_KEY: ${{AUTHENTIK_SECRET_KEY}}
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
