"""Pydantic request/response models for the DataSphere API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    mode: Literal["explicit", "recommended"] = Field("explicit", description="Mode de génération")
    # Mode 1 — explicit
    business_request: Optional[str] = Field(None, max_length=2000)
    cloud_provider: Optional[str] = None
    data_warehouse: Optional[str] = None
    orchestrator: Optional[str] = None
    ingestion: Optional[str] = None
    transformation: Optional[str] = None
    bi_tool: Optional[str] = None
    deployment: Optional[str] = None
    data_lake: Optional[str] = None
    catalog: Optional[str] = None
    quality: Optional[str] = None
    security: list[str] = []
    budget: Optional[str] = "medium"
    data_volume: Optional[str] = "medium"
    processing_mode: Optional[str] = "batch"
    region: Optional[str] = None
    # Mode 2 — recommended only
    security_level: Optional[str] = "rbac"
    team_size: Optional[str] = "medium"
    cloud_preference: Optional[str] = "none"
    deployment_preference: Optional[str] = None
    must_be_open_source: bool = False
    existing_tools: list[str] = []
    compliance_requirements: list[str] = []


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str = ""


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[dict] = None
    error: str = ""


class ProposalsRequest(BaseModel):
    cloud_provider: str = "aws"
    budget: str = "medium"
    data_volume: str = "medium"
    processing_mode: str = "batch"
    deployment: str = "kubernetes"
    security: list[str] = ["RBAC"]


class DbtGenerateRequest(BaseModel):
    business_request: str = Field(..., min_length=3, max_length=2000)
    cloud_provider: str = "aws"
    data_warehouse: str = "snowflake"
    orchestrator: str = "airflow"
    ingestion: str = "airbyte"
    transformation: str = "dbt"
    bi_tool: str = "superset"
    deployment: str = "kubernetes"
    security: list[str] = ["RBAC"]
    budget: str = "medium"


class DagGenerateRequest(BaseModel):
    business_request: str = Field(..., min_length=3, max_length=2000)
    cloud_provider: str = "aws"
    data_warehouse: str = "snowflake"
    orchestrator: str = "airflow"
    ingestion: str = "airbyte"
    transformation: str = "dbt"
    bi_tool: str = "superset"
    deployment: str = "kubernetes"
    quality: Optional[str] = "great-expectations"
    security: list[str] = ["RBAC"]
    budget: str = "medium"
    processing_mode: str = "batch"


class LineageRequest(BaseModel):
    stack: dict
    business_request: str = ""


class CostEstimateRequest(BaseModel):
    stack: dict  # validated_stack dict
    budget: str = "medium"


class StackDiffRequest(BaseModel):
    from_stack: dict
    to_stack: dict


class WebhookRegisterRequest(BaseModel):
    url: str = Field(..., description="URL to POST to when events fire")
    events: list[str] = Field(default=["*"], description="Events: job.completed, job.failed, or *")
    secret: str = Field(default="", description="Optional HMAC signing secret")


class TemplateGenerateRequest(BaseModel):
    template_id: str
    business_request: str = Field(..., min_length=3, max_length=2000)
    overrides: dict = Field(default_factory=dict)
