from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("security", "keycloak")
class KeycloakAdapter(BaseAdapter):
    name = "keycloak"
    category = "security"

    def connect(self):
        from keycloak import KeycloakOpenID
        return KeycloakOpenID(
            server_url=f"http://{self.config.host or 'localhost'}:{self.config.port or 8080}",
            realm_name=self.config.extra.get("realm", "master"),
            client_id=self.config.extra.get("client_id", "datasphere"),
        )

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  keycloak:
    image: quay.io/keycloak/keycloak:23.0
    command: start-dev
    environment:
      KEYCLOAK_ADMIN: ${{KEYCLOAK_ADMIN:-admin}}
      KEYCLOAK_ADMIN_PASSWORD: ${{KEYCLOAK_ADMIN_PASSWORD}}
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgresql/keycloak
      KC_DB_USERNAME: ${{POSTGRES_USER}}
      KC_DB_PASSWORD: ${{POSTGRES_PASSWORD}}
    ports:
      - "{self.config.port or 8080}:8080"
    depends_on:
      - postgresql
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
