from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("warehouse", "postgresql")
class PostgreSQLAdapter(BaseAdapter):
    name = "postgresql"
    category = "warehouse"

    def connect(self):
        import psycopg2
        return psycopg2.connect(
            host=self.config.host,
            port=self.config.port or 5432,
            dbname=self.config.database,
            user=self.config.username,
            password=self.config.password,
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("postgresql: host is required")
        if not self.config.database:
            errors.append("postgresql: database is required")
        return errors

    def deploy(self) -> str:
        return f"""  postgresql:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: {self.config.database or "datasphere"}
      POSTGRES_USER: {self.config.username or "datasphere"}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD}}
    ports:
      - "{self.config.port or 5432}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {self.config.username or "datasphere"}"]
      interval: 10s
      timeout: 5s
      retries: 5
"""

    def status(self):
        try:
            conn = self.connect()
            conn.close()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
