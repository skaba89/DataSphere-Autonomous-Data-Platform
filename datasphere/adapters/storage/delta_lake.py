from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("storage", "delta-lake")
class DeltaLakeAdapter(BaseAdapter):
    name = "delta-lake"
    category = "storage"

    def connect(self):
        import deltalake
        path = self.config.extra.get("path", "/tmp/delta")
        return deltalake.DeltaTable(path)

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return (
            "# Delta Lake is a storage layer — no separate service required.\n"
            "# Install: pip install deltalake\n"
            "# Works on top of S3, ADLS, GCS, or local filesystem.\n"
            "# With Spark: spark.conf.set('spark.sql.extensions', 'io.delta.sql.DeltaSparkSessionExtension')\n"
        )

    def status(self):
        try:
            import importlib
            importlib.import_module("deltalake")
            return {"adapter": self.name, "status": "installed"}
        except ImportError:
            return {"adapter": self.name, "status": "not_installed", "error": "pip install deltalake"}
