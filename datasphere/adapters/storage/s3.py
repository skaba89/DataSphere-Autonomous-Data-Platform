from __future__ import annotations
from datasphere.adapters.base import BaseAdapter
from datasphere.core.registry import registry


@registry.register("storage", "s3")
class S3Adapter(BaseAdapter):
    name = "s3"
    category = "storage"

    def connect(self):
        import boto3
        return boto3.client(
            "s3",
            region_name=self.config.extra.get("region", "us-east-1"),
            aws_access_key_id=self.config.username,
            aws_secret_access_key=self.config.password,
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.config.extra.get("region"):
            errors.append("s3: region is required in extra.region")
        return errors

    def deploy(self) -> str:
        return "# AWS S3 is a managed service — configure credentials via IAM role or environment variables."

    def status(self):
        return {"adapter": self.name, "status": "managed-saas"}
