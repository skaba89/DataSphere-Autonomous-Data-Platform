from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("bi", "superset")
class SupersetAdapter(BaseAdapter):
    name = "superset"
    category = "bi"

    def connect(self):
        import requests
        session = requests.Session()
        base = f"http://{self.config.host or 'localhost'}:{self.config.port or 8088}"
        r = session.post(f"{base}/api/v1/security/login", json={
            "username": self.config.username or "admin",
            "password": self.config.password or "admin",
            "provider": "db",
        })
        if r.status_code == 200:
            session.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        return session

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  superset:
    image: apache/superset:latest
    ports:
      - "{self.config.port or 8088}:8088"
    environment:
      SUPERSET_SECRET_KEY: ${{SUPERSET_SECRET_KEY}}
      DATABASE_URL: postgresql+psycopg2://${{POSTGRES_USER}}:${{POSTGRES_PASSWORD}}@postgresql/superset
    depends_on:
      - postgresql
    command: >
      sh -c "superset db upgrade &&
             superset fab create-admin --username admin --firstname Admin --lastname User --email admin@example.com --password ${{SUPERSET_ADMIN_PASSWORD}} &&
             superset init &&
             superset run -h 0.0.0.0 -p 8088"
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
