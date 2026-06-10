from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("bi", "metabase")
class MetabaseAdapter(BaseAdapter):
    name = "metabase"
    category = "bi"

    def connect(self):
        import requests
        return requests.Session()

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return f"""  metabase:
    image: metabase/metabase:latest
    ports:
      - "{self.config.port or 3000}:3000"
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: metabase
      MB_DB_PORT: 5432
      MB_DB_USER: ${{POSTGRES_USER}}
      MB_DB_PASS: ${{POSTGRES_PASSWORD}}
      MB_DB_HOST: postgresql
    depends_on:
      - postgresql
    volumes:
      - metabase_data:/metabase-data
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
