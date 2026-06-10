from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("warehouse", "duckdb")
class DuckDBAdapter(BaseAdapter):
    name = "duckdb"
    category = "warehouse"

    def connect(self):
        import duckdb
        path = self.config.extra.get("path", ":memory:")
        return duckdb.connect(path)

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return "# DuckDB is an embedded database — no server deployment needed.\n# Set path in stack.yaml extra.path."

    def status(self):
        try:
            conn = self.connect()
            conn.execute("SELECT 1")
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
