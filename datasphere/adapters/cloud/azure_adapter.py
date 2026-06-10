from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("cloud", "azure")
class AzureAdapter(BaseAdapter):
    name = "azure"
    category = "cloud"

    def connect(self):
        from azure.identity import DefaultAzureCredential
        return DefaultAzureCredential()

    def validate(self) -> list[str]:
        if not self.config.extra.get("subscription_id"):
            return ["azure: subscription_id is required in extra.subscription_id"]
        return []

    def deploy(self) -> str:
        return "# Azure: use Terraform modules in infra/terraform/modules/azure/"

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
