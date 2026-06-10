from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("warehouse", "snowflake")
class SnowflakeAdapter(BaseAdapter):
    name = "snowflake"
    category = "warehouse"

    def connect(self):
        import snowflake.connector
        return snowflake.connector.connect(
            account=self.config.extra.get("account", ""),
            user=self.config.username,
            password=self.config.password,
            database=self.config.database,
            warehouse=self.config.extra.get("warehouse", ""),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.extra.get("account"):
            errors.append("snowflake: account is required")
        if not self.config.username:
            errors.append("snowflake: username is required")
        return errors

    def deploy(self) -> str:
        return "# Snowflake is a managed SaaS — no local deployment needed.\n# Configure credentials in stack.yaml."

    def status(self):
        return {"adapter": self.name, "status": "managed-saas"}
