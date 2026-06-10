from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("orchestration", "dagster")
class DagsterAdapter(BaseAdapter):
    name = "dagster"
    category = "orchestration"

    def connect(self):
        from dagster_graphql import DagsterGraphQLClient
        return DagsterGraphQLClient(
            hostname=self.config.host,
            port_number=self.config.port or 3000,
        )

    def validate(self) -> list[str]:
        if not self.config.host:
            return ["dagster: host is required"]
        return []

    def deploy(self) -> str:
        return f"""  dagster-webserver:
    image: ghcr.io/dagster-io/dagster:latest
    ports:
      - "{self.config.port or 3000}:3000"
    environment:
      DAGSTER_HOME: /opt/dagster/dagster_home
    volumes:
      - dagster_home:/opt/dagster/dagster_home
      - ./pipeline:/opt/dagster/app
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
