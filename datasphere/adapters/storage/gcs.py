from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("storage", "gcs")
class GCSAdapter(BaseAdapter):
    name = "gcs"
    category = "storage"

    def connect(self):
        from google.cloud import storage
        return storage.Client(project=self.config.extra.get("project"))

    def validate(self) -> list[str]:
        if not self.config.extra.get("project"):
            return ["gcs: project is required in extra.project"]
        return []

    def deploy(self) -> str:
        return "# GCS is a managed GCP service — set GOOGLE_APPLICATION_CREDENTIALS or use Workload Identity."

    def status(self):
        return {"adapter": self.name, "status": "managed-saas"}
