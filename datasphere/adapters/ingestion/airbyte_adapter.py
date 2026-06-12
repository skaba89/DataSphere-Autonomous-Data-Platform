from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("ingestion", "airbyte")
class AirbyteAdapter(BaseAdapter):
    name = "airbyte"
    category = "ingestion"

    def connect(self):
        import requests
        session = requests.Session()
        session.auth = (self.config.username or "airbyte", self.config.password or "password")
        session.base_url = f"http://{self.config.host or 'localhost'}:{self.config.port or 8000}/api/v1"
        return session

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  airbyte-server:
    image: airbyte/server:latest
    ports:
      - "{self.config.port or 8001}:8001"
    environment:
      DATABASE_URL: jdbc:postgresql://postgresql:5432/airbyte
      DATABASE_USER: ${{POSTGRES_USER}}
      DATABASE_PASSWORD: ${{POSTGRES_PASSWORD}}
    depends_on:
      - postgresql

  airbyte-webapp:
    image: airbyte/webapp:latest
    ports:
      - "8000:80"
    environment:
      AIRBYTE_SERVER_HOST: airbyte-server
      AIRBYTE_SERVER_PORT: 8001
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
