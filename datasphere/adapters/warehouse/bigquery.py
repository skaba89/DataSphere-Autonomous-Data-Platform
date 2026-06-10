from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("warehouse", "bigquery")
class BigQueryAdapter(BaseAdapter):
    name = "bigquery"
    category = "warehouse"

    def connect(self):
        from google.cloud import bigquery
        project = self.config.extra.get("project", "")
        return bigquery.Client(project=project)

    def validate(self) -> list[str]:
        errors = []
        if not self.config.extra.get("project"):
            errors.append("bigquery: project is required")
        return errors

    def deploy(self) -> str:
        return "# BigQuery is a managed GCP service — no local deployment needed.\n# Set GOOGLE_APPLICATION_CREDENTIALS or use Workload Identity."

    def status(self):
        return {"adapter": self.name, "status": "managed-saas"}
