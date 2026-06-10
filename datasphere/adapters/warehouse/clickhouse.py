from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("warehouse", "clickhouse")
class ClickHouseAdapter(BaseAdapter):
    name = "clickhouse"
    category = "warehouse"

    def connect(self):
        import clickhouse_connect
        return clickhouse_connect.get_client(
            host=self.config.host,
            port=self.config.port or 8123,
            username=self.config.username or "default",
            password=self.config.password,
        )

    def validate(self) -> list[str]:
        if not self.config.host:
            return ["clickhouse: host is required"]
        return []

    def deploy(self) -> str:
        return f"""  clickhouse:
    image: clickhouse/clickhouse-server:23.8
    ports:
      - "{self.config.port or 8123}:8123"
      - "9000:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
"""

    def status(self):
        try:
            client = self.connect()
            client.query("SELECT 1")
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
