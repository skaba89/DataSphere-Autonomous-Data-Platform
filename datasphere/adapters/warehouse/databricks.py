from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("warehouse", "databricks")
class DatabricksAdapter(BaseAdapter):
    name = "databricks"
    category = "warehouse"

    def connect(self):
        from databricks import sql as dbsql
        return dbsql.connect(
            server_hostname=self.config.host,
            http_path=self.config.extra.get("http_path", "/sql/1.0/warehouses/default"),
            access_token=self.config.password,
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("databricks: workspace hostname is required")
        if not self.config.password:
            errors.append("databricks: access token (password) is required")
        return errors

    def deploy(self) -> str:
        return (
            "# Databricks is a managed SaaS platform (AWS/Azure/GCP).\n"
            "# Provision workspace via Terraform: databricks_mws_workspaces\n"
            f"# Workspace: https://{self.config.host or '<account>.azuredatabricks.net'}\n"
        )

    def status(self):
        try:
            conn = self.connect()
            conn.close()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
