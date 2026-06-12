from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("storage", "adls")
class ADLSAdapter(BaseAdapter):
    name = "adls"
    category = "storage"

    def connect(self):
        from azure.storage.filedatalake import DataLakeServiceClient
        account_name = self.config.extra.get("account_name") or self.config.host
        account_key = self.config.password
        return DataLakeServiceClient(
            account_url=f"https://{account_name}.dfs.core.windows.net",
            credential=account_key,
        )

    def validate(self) -> list[str]:
        errors = []
        if not (self.config.extra.get("account_name") or self.config.host):
            errors.append("adls: account_name (or host) is required")
        if not self.config.password:
            errors.append("adls: account_key (password) is required")
        return errors

    def deploy(self) -> str:
        return (
            "# Azure Data Lake Storage Gen2 is a managed Azure service.\n"
            "# Terraform resource: azurerm_storage_account with is_hns_enabled=true\n"
            "# + azurerm_storage_data_lake_gen2_filesystem\n"
        )

    def status(self):
        try:
            client = self.connect()
            list(client.list_file_systems())
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
