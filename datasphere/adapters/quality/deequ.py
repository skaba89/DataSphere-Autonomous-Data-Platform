from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("quality", "deequ")
class DeequAdapter(BaseAdapter):
    name = "deequ"
    category = "quality"

    def connect(self):
        return {"status": "deequ requires a SparkSession — use SparkAdapter first"}

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return (
            "# AWS Deequ runs on Spark — no dedicated service.\n"
            "# Add to Spark: --packages com.amazon.deequ:deequ:2.0.7-spark-3.5\n"
            "# Python bindings: pip install pydeequ\n"
        )

    def status(self):
        try:
            import importlib
            importlib.import_module("pydeequ")
            return {"adapter": self.name, "status": "installed"}
        except ImportError:
            return {"adapter": self.name, "status": "not_installed", "error": "pip install pydeequ"}
