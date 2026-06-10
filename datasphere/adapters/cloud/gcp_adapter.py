from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("cloud", "gcp")
class GCPAdapter(BaseAdapter):
    name = "gcp"
    category = "cloud"

    def connect(self):
        from google.auth import default
        credentials, project = default()
        return credentials

    def validate(self) -> list[str]:
        if not self.config.extra.get("project"):
            return ["gcp: project is required in extra.project"]
        return []

    def deploy(self) -> str:
        return "# GCP: use Terraform modules in infra/terraform/modules/gcp/"

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
