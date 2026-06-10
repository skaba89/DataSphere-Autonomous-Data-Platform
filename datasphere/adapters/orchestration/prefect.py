from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("orchestration", "prefect")
class PrefectAdapter(BaseAdapter):
    name = "prefect"
    category = "orchestration"

    def connect(self):
        import prefect.client
        return prefect.client.get_client()

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  prefect-server:
    image: prefecthq/prefect:2-latest
    command: prefect server start --host 0.0.0.0
    ports:
      - "{self.config.port or 4200}:4200"
    environment:
      PREFECT_SERVER_API_HOST: 0.0.0.0
      PREFECT_API_DATABASE_CONNECTION_URL: postgresql+asyncpg://${{POSTGRES_USER}}:${{POSTGRES_PASSWORD}}@postgresql/prefect
    depends_on:
      - postgresql
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
