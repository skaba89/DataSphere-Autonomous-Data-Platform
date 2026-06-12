from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("ai", "azure-openai")
class AzureOpenAIAdapter(BaseAdapter):
    name = "azure-openai"
    category = "ai"

    def connect(self):
        from openai import AzureOpenAI
        return AzureOpenAI(
            api_key=self.config.password,
            azure_endpoint=f"https://{self.config.host or self.config.extra.get('resource_name', 'myresource')}.openai.azure.com",
            api_version=self.config.extra.get("api_version", "2024-02-01"),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.password:
            errors.append("azure-openai: API key (password) is required")
        if not (self.config.host or self.config.extra.get("resource_name")):
            errors.append("azure-openai: resource name (host) is required")
        return errors

    def deploy(self) -> str:
        return (
            "# Azure OpenAI Service — provision via Azure Portal or Terraform.\n"
            "# Terraform: azurerm_cognitive_account (kind=OpenAI)\n"
            "# Deploy a model: azurerm_cognitive_deployment\n"
        )

    def status(self):
        try:
            client = self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
