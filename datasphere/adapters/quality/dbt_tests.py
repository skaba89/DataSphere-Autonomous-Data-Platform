from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("quality", "dbt-tests")
class DbtTestsAdapter(BaseAdapter):
    name = "dbt-tests"
    category = "quality"

    def connect(self):
        project_path = self.config.extra.get("project_path", ".")
        return {"project_path": project_path}

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return (
            "# dbt tests are embedded in your dbt project — no separate service.\n"
            "# Run: dbt test\n"
            "# Define tests in schema.yml:\n"
            "#   columns:\n"
            "#     - name: id\n"
            "#       tests: [not_null, unique]\n"
        )

    def status(self):
        try:
            import importlib
            importlib.import_module("dbt")
            return {"adapter": self.name, "status": "installed"}
        except ImportError:
            return {"adapter": self.name, "status": "not_installed", "error": "pip install dbt-core"}
