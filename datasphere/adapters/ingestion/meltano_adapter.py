from __future__ import annotations
import subprocess
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("ingestion", "meltano")
class MeltanoAdapter(BaseAdapter):
    name = "meltano"
    category = "ingestion"

    def connect(self):
        return subprocess.run

    def validate(self) -> list[str]:
        try:
            result = subprocess.run(["meltano", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                return ["meltano: binary not found — pip install meltano"]
        except FileNotFoundError:
            return ["meltano: binary not found — pip install meltano"]
        return []

    def deploy(self) -> str:
        return "# Meltano runs as a CLI — add it to your project with: pip install meltano && meltano init"

    def run(self, command: str, project_dir: str = ".") -> subprocess.CompletedProcess:
        return subprocess.run(
            ["meltano"] + command.split(),
            cwd=project_dir,
            capture_output=True,
            text=True,
        )

    def status(self):
        errors = self.validate()
        return {"adapter": self.name, "status": "available" if not errors else "unavailable"}
