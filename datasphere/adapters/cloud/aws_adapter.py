from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("cloud", "aws")
class AWSAdapter(BaseAdapter):
    name = "aws"
    category = "cloud"

    def connect(self):
        import boto3
        return boto3.Session(
            region_name=self.config.extra.get("region", "us-east-1"),
            aws_access_key_id=self.config.username or None,
            aws_secret_access_key=self.config.password or None,
        )

    def validate(self) -> list[str]:
        if not self.config.extra.get("region"):
            return ["aws: region is required in extra.region"]
        return []

    def deploy(self) -> str:
        return "# AWS: use Terraform modules in infra/terraform/modules/aws/"

    def status(self):
        try:
            session = self.connect()
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            return {"adapter": self.name, "status": "authenticated", "account": identity["Account"]}
        except Exception as e:
            return {"adapter": self.name, "status": "unauthenticated", "error": str(e)}
