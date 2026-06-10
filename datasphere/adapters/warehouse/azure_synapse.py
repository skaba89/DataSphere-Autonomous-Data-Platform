from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("warehouse", "azure-synapse")
class AzureSynapseAdapter(BaseAdapter):
    name = "azure-synapse"
    category = "warehouse"

    def connect(self):
        import pyodbc
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.config.host},1433;"
            f"DATABASE={self.config.database or 'master'};"
            f"UID={self.config.username};"
            f"PWD={self.config.password};"
            "Encrypt=yes;TrustServerCertificate=no;"
        )
        return pyodbc.connect(conn_str)

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("azure-synapse: server endpoint (host) is required")
        if not self.config.username:
            errors.append("azure-synapse: username is required")
        return errors

    def deploy(self) -> str:
        return (
            "# Azure Synapse Analytics is a managed Azure service.\n"
            "# Provision via Terraform: azurerm_synapse_workspace + azurerm_synapse_sql_pool\n"
            f"# Endpoint: {self.config.host or '<workspace>.sql.azuresynapse.net'}:1433\n"
        )

    def status(self):
        try:
            conn = self.connect()
            conn.close()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
