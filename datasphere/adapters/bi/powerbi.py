from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("bi", "powerbi")
class PowerBIAdapter(BaseAdapter):
    name = "powerbi"
    category = "bi"

    def connect(self):
        import urllib.request
        tenant_id = self.config.extra.get("tenant_id", "common")
        url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        return {"endpoint": url, "status": "configured"}

    def validate(self) -> list[str]:
        errors = []
        if not self.config.extra.get("tenant_id"):
            errors.append("powerbi: tenant_id is required in extra config")
        if not self.config.extra.get("client_id"):
            errors.append("powerbi: client_id is required in extra config")
        return errors

    def deploy(self) -> str:
        return (
            "# Power BI is a Microsoft SaaS service — no local deployment.\n"
            "# Requires Power BI Pro or Premium license.\n"
            "# Configure via Azure AD app registration for API access.\n"
            "# REST API: https://api.powerbi.com/v1.0/myorg\n"
        )

    def status(self):
        return {"adapter": self.name, "status": "saas", "note": "Power BI is cloud-only"}
