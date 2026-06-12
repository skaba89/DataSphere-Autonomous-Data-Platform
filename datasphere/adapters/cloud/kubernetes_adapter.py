from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("cloud", "kubernetes")
class KubernetesAdapter(BaseAdapter):
    name = "kubernetes"
    category = "cloud"

    def connect(self):
        from kubernetes import client, config as k8s_config
        k8s_config.load_kube_config(config_file=self.config.extra.get("kubeconfig"))
        return client.CoreV1Api()

    def validate(self) -> list[str]:
        return []

    def deploy(self) -> str:
        return "# Kubernetes: use Helm charts in infra/helm/datasphere/"

    def status(self):
        try:
            v1 = self.connect()
            nodes = v1.list_node()
            return {"adapter": self.name, "status": "healthy", "nodes": len(nodes.items)}
        except Exception as e:
            return {"adapter": self.name, "status": "unhealthy", "error": str(e)}
