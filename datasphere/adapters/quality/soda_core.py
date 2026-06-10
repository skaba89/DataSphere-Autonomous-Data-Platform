from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("quality", "soda-core")
class SodaCoreAdapter(BaseAdapter):
    name = "soda-core"
    category = "quality"

    def connect(self):
        from soda.scan import Scan
        return Scan()

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return (
            "# Soda Core runs as a Python CLI tool — no dedicated service.\n"
            "# Install: pip install soda-core-postgres  # or soda-core-bigquery, etc.\n"
            "# Run:     soda scan -d my_datasource -c configuration.yml checks.yml\n"
        )

    def status(self):
        try:
            import importlib
            importlib.import_module("soda")
            return {"adapter": self.name, "status": "installed"}
        except ImportError:
            return {"adapter": self.name, "status": "not_installed", "error": "pip install soda-core"}
