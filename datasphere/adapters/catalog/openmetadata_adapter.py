from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("catalog", "openmetadata")
class OpenMetadataAdapter(BaseAdapter):
    name = "openmetadata"
    category = "catalog"

    def connect(self):
        from metadata.ingestion.ometa.ometa_api import OpenMetadata
        from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import OpenMetadataConnection
        from metadata.generated.schema.security.client.openMetadataJWTClientConfig import OpenMetadataJWTClientConfig
        server_config = OpenMetadataConnection(
            hostPort=f"http://{self.config.host or 'localhost'}:{self.config.port or 8585}/api",
            authProvider="openmetadata",
            securityConfig=OpenMetadataJWTClientConfig(jwtToken=self.config.password or ""),
        )
        return OpenMetadata(server_config)

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  openmetadata-server:
    image: openmetadata/server:latest
    ports:
      - "{self.config.port or 8585}:8585"
      - "8586:8586"
    environment:
      DB_HOST: postgresql
      DB_PORT: 5432
      DB_USER: ${{POSTGRES_USER}}
      DB_USER_PASSWORD: ${{POSTGRES_PASSWORD}}
      DB_DRIVER_CLASS: org.postgresql.Driver
      DB_SCHEME: postgresql
    depends_on:
      - postgresql
      - elasticsearch
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
