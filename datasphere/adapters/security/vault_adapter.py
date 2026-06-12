from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("security", "vault")
class VaultAdapter(BaseAdapter):
    name = "vault"
    category = "security"

    def connect(self):
        import hvac
        client = hvac.Client(
            url=f"http://{self.config.host or 'localhost'}:{self.config.port or 8200}",
            token=self.config.password,
        )
        return client

    def validate(self) -> list[str]:
        if not self.config.password:
            return ["vault: token (password) is required"]
        return []

    def deploy(self) -> str:
        return f"""  vault:
    image: hashicorp/vault:latest
    ports:
      - "{self.config.port or 8200}:8200"
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: ${{VAULT_TOKEN}}
      VAULT_DEV_LISTEN_ADDRESS: 0.0.0.0:8200
    cap_add:
      - IPC_LOCK
    volumes:
      - vault_data:/vault/data
"""

    def status(self):
        try:
            client = self.connect()
            return {"adapter": self.name, "status": "healthy" if client.is_authenticated() else "unauthenticated"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
