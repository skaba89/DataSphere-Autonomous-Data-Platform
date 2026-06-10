from __future__ import annotations
import subprocess
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("transformation", "dbt")
class DbtAdapter(BaseAdapter):
    name = "dbt"
    category = "transformation"

    def connect(self):
        return subprocess.run

    def validate(self) -> list[str]:
        try:
            result = subprocess.run(["dbt", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                return ["dbt: binary not found — install dbt-core"]
        except FileNotFoundError:
            return ["dbt: binary not found — install dbt-core"]
        return []

    def deploy(self) -> str:
        return """# dbt runs as a CLI tool, typically in a CI/CD pipeline or scheduled job.
# Example Dockerfile snippet:
# FROM python:3.11-slim
# RUN pip install dbt-core dbt-postgres
# COPY . /dbt
# WORKDIR /dbt
# CMD ["dbt", "run"]
"""

    def run(self, command: str, project_dir: str = ".") -> subprocess.CompletedProcess:
        return subprocess.run(
            ["dbt"] + command.split(),
            cwd=project_dir,
            capture_output=True,
            text=True,
        )

    def status(self):
        errors = self.validate()
        return {"adapter": self.name, "status": "available" if not errors else "unavailable"}
