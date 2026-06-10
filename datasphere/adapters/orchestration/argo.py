from __future__ import annotations
from datasphere.adapters.base import BaseAdapter, AdapterConfig
from datasphere.core.registry import registry


@registry.register("orchestration", "argo")
class ArgoWorkflowsAdapter(BaseAdapter):
    name = "argo"
    category = "orchestration"

    def connect(self):
        import urllib.request
        url = f"http://{self.config.host or 'localhost'}:{self.config.port or 2746}/api/v1/info"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.read()

    def validate(self) -> list[str]:
        errors = []
        if not self.config.host:
            errors.append("argo: host is required (Argo Workflows server address)")
        return errors

    def deploy(self) -> str:
        return (
            "# Argo Workflows — deploy on Kubernetes:\n"
            "# kubectl create namespace argo\n"
            "# kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/latest/download/install.yaml\n"
            f"# UI: http://{self.config.host or 'localhost'}:{self.config.port or 2746}\n"
        )

    def status(self):
        try:
            self.connect()
            return {"adapter": self.name, "status": "healthy"}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
