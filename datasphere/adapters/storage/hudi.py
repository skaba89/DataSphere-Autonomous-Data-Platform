from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("storage", "hudi")
class HudiAdapter(BaseAdapter):
    name = "hudi"
    category = "storage"

    def connect(self):
        return {"status": "hudi requires Spark session — use SparkAdapter first"}

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return (
            "# Apache Hudi is a storage layer running on top of Spark.\n"
            "# Add to Spark: --packages org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0\n"
            "# Configure: hoodie.datasource.write.table.type=COPY_ON_WRITE\n"
        )

    def status(self):
        return {"adapter": self.name, "status": "library_only"}
