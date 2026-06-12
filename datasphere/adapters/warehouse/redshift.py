from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("warehouse", "redshift")
class RedshiftAdapter(BaseAdapter):
    name = "redshift"
    category = "warehouse"

    def connect(self):
        import psycopg2
        return psycopg2.connect(
            host=self.config.host,
            port=self.config.port or 5439,
            dbname=self.config.database or "dev",
            user=self.config.username,
            password=self.config.password,
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("redshift: cluster endpoint (host) is required")
        if not self.config.username:
            errors.append("redshift: username is required")
        return errors

    def deploy(self) -> str:
        return (
            "# Redshift is a managed AWS service — provision via Terraform or AWS Console.\n"
            "# Terraform resource: aws_redshift_cluster\n"
            f"# Endpoint: {self.config.host or '<cluster>.region.redshift.amazonaws.com'}:{self.config.port or 5439}\n"
        )

    def status(self):
        try:
            conn = self.connect()
            conn.close()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
