from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("vector", "pgvector")
class PgVectorAdapter(BaseAdapter):
    name = "pgvector"
    category = "vector"

    def connect(self):
        import psycopg2
        conn = psycopg2.connect(
            host=self.config.host,
            port=self.config.port or 5432,
            dbname=self.config.database,
            user=self.config.username,
            password=self.config.password,
        )
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()
        return conn

    def validate(self) -> list[str]:
        if not self.config.host:
            return ["pgvector: host is required"]
        return []

    def deploy(self) -> str:
        return f"""  pgvector:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: {self.config.database or "vectors"}
      POSTGRES_USER: {self.config.username or "datasphere"}
      POSTGRES_PASSWORD: ${{PGVECTOR_PASSWORD}}
    ports:
      - "{self.config.port or 5432}:5432"
    volumes:
      - pgvector_data:/var/lib/postgresql/data
"""

    def status(self):
        return {"adapter": self.name, "status": "unknown"}
