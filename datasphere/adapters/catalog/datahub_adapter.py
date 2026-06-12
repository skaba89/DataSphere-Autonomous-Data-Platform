from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("catalog", "datahub")
class DataHubAdapter(BaseAdapter):
    name = "datahub"
    category = "catalog"

    def connect(self):
        from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph
        return DataHubGraph(DatahubClientConfig(
            server=f"http://{self.config.host or 'localhost'}:{self.config.port or 8080}",
            token=self.config.password,
        ))

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  datahub-gms:
    image: linkedin/datahub-gms:latest
    ports:
      - "{self.config.port or 8080}:8080"
    environment:
      DATAHUB_SERVER_TYPE: quickstart
    depends_on:
      - postgresql
      - elasticsearch
      - kafka
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
