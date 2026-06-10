from __future__ import annotations
import subprocess
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("cloud", "local-docker")
class LocalDockerAdapter(BaseAdapter):
    name = "local-docker"
    category = "cloud"

    def connect(self):
        import docker
        return docker.from_env()

    def validate(self) -> list[str]:
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, text=True)
            if result.returncode != 0:
                return ["local-docker: Docker daemon not running"]
        except FileNotFoundError:
            return ["local-docker: docker binary not found"]
        return []

    def deploy(self) -> str:
        return "# Local Docker: run 'docker compose up -d' from the infra/docker directory."

    def status(self):
        try:
            import docker
            client = docker.from_env()
            info = client.info()
            return {"adapter": self.name, "status": "healthy", "containers": info["Containers"]}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
