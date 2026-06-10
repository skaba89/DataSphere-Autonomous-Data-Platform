from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("bi", "tableau")
class TableauAdapter(BaseAdapter):
    name = "tableau"
    category = "bi"

    def connect(self):
        import tableauserverclient as TSC
        tableau_auth = TSC.TableauAuth(
            self.config.username,
            self.config.password,
            site_id=self.config.extra.get("site_id", ""),
        )
        server = TSC.Server(f"https://{self.config.host}", use_server_version=True)
        server.auth.sign_in(tableau_auth)
        return server

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("tableau: server host is required")
        if not self.config.username:
            errors.append("tableau: username is required")
        if not self.config.password:
            errors.append("tableau: password is required")
        return errors

    def deploy(self) -> str:
        return (
            "# Tableau Server or Tableau Cloud — commercial license required.\n"
            "# Self-hosted: Linux installer at https://www.tableau.com/support/releases/server\n"
            "# Cloud: https://online.tableau.com\n"
            "# Open-source alternative: Apache Superset or Metabase\n"
        )

    def status(self):
        try:
            server = self.connect()
            server.auth.sign_out()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
