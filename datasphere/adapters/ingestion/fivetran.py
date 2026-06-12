from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("ingestion", "fivetran")
class FivetranAdapter(BaseAdapter):
    name = "fivetran"
    category = "ingestion"

    def connect(self):
        import urllib.request
        import base64
        token = base64.b64encode(
            f"{self.config.username}:{self.config.password}".encode()
        ).decode()
        req = urllib.request.Request(
            "https://api.fivetran.com/v1/connectors",
            headers={"Authorization": f"Basic {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.username:
            errors.append("fivetran: API key (username) is required")
        if not self.config.password:
            errors.append("fivetran: API secret (password) is required")
        return errors

    def deploy(self) -> str:
        return (
            "# Fivetran is a fully managed SaaS ELT service.\n"
            "# Configure connectors at https://fivetran.com/dashboard\n"
            "# No local deployment required.\n"
        )

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
