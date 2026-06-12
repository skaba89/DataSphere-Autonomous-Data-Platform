"""Shared generation utilities: _run_generation, _serialize_result, _build_stack_report."""
from __future__ import annotations

import tempfile
import time
from typing import Any

from datasphere.api.logging_config import get_logger, set_request_id
from datasphere.api.tracing import start_span
from datasphere.api.job_store import job_store
from datasphere.api.artifact_store import artifact_store
from datasphere.api.metrics import metrics
from datasphere.api.webhooks import webhook_registry
from datasphere.api.tenancy import get_tenant_id
from datasphere.api.notifications import notification_service
from datasphere.models.modes import ExplicitStack, RecommendationContext
from datasphere.agents.mode_router import run_explicit, run_recommended
from datasphere.api.models import GenerateRequest

_log = get_logger(__name__)


def _run_generation(job_id: str, req: GenerateRequest) -> None:
    set_request_id(job_id)
    _log.info("generation_started", extra={"job_id": job_id, "mode": req.mode})
    job_store.update(job_id, status="running")
    job_start = time.time()
    with start_span("generation.run", {"job_id": job_id, "mode": req.mode}):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                if req.mode == "explicit":
                    stack = ExplicitStack(
                        business_request=req.business_request or "DataSphere pipeline",
                        cloud_provider=req.cloud_provider or "aws",
                        data_warehouse=req.data_warehouse or "snowflake",
                        orchestrator=req.orchestrator or "airflow",
                        ingestion=req.ingestion or "airbyte",
                        transformation=req.transformation or "dbt",
                        bi_tool=req.bi_tool or "superset",
                        deployment=req.deployment or "kubernetes",
                        data_lake=req.data_lake,
                        catalog=req.catalog,
                        quality=req.quality,
                        security=req.security,
                        budget=req.budget or "medium",
                        data_volume=req.data_volume or "medium",
                        processing_mode=req.processing_mode or "batch",
                        region=req.region,
                    )
                    result = run_explicit(stack, output_dir=tmp, verbose=False)
                else:
                    ctx = RecommendationContext(
                        business_request=req.business_request or "DataSphere pipeline",
                        budget=req.budget or "medium",
                        data_volume=req.data_volume or "medium",
                        security_level=req.security_level or "rbac",
                        team_size=req.team_size or "medium",
                        processing_mode=req.processing_mode or "batch",
                        cloud_preference=req.cloud_preference or "none",
                        deployment_preference=req.deployment_preference,
                        must_be_open_source=req.must_be_open_source,
                        existing_tools=req.existing_tools,
                        compliance_requirements=req.compliance_requirements,
                    )
                    result = run_recommended(ctx, output_dir=tmp, verbose=False)

                serialized = _serialize_result(result)

                # Persist generated files to artifact store
                all_files: dict[str, str] = {}
                for agent_name in ("infrastructure", "deployment"):
                    agent_out = getattr(result, agent_name, None)
                    if agent_out and agent_out.artifacts:
                        for fname, content in agent_out.artifacts.items():
                            all_files[f"{agent_name}/{fname}"] = str(content)
                if all_files:
                    try:
                        artifact_store.save_files(job_id, all_files)
                        serialized["artifact_count"] = len(all_files)
                    except Exception as exc:
                        _log.warning("artifact_save_failed job=%s error=%s", job_id, exc)

                job_store.update(job_id, status="completed", result=serialized)
                metrics.record_job_completed(mode=req.mode, duration_s=time.time() - job_start)
                _log.info("generation_completed", extra={"job_id": job_id, "success": result.success})
                webhook_registry.fire("job.completed", job_id, get_tenant_id(), {"success": True})
                job_meta = job_store.get(job_id) or {}
                meta = job_meta.get("meta", {})
                notification_service.notify_async(
                    job_id=job_id,
                    status="completed",
                    result=serialized,
                    duration_s=time.time() - job_start,
                    tenant_id=meta.get("tenant_id", "default"),
                    slack_url=meta.get("slack_webhook", ""),
                    teams_url=meta.get("teams_webhook", ""),
                )
        except Exception as exc:
            _log.exception("generation_failed", extra={"job_id": job_id, "error": str(exc)})
            job_store.update(job_id, status="failed", error=str(exc))
            metrics.record_job_failed(mode=req.mode)
            webhook_registry.fire("job.failed", job_id, get_tenant_id(), {"error": str(exc)})
            job_meta = job_store.get(job_id) or {}
            meta = job_meta.get("meta", {})
            notification_service.notify_async(
                job_id=job_id,
                status="failed",
                result=None,
                duration_s=time.time() - job_start,
                tenant_id=meta.get("tenant_id", "default"),
                slack_url=meta.get("slack_webhook", ""),
                teams_url=meta.get("teams_webhook", ""),
            )


def _serialize_result(result: Any) -> dict:
    out: dict[str, Any] = {
        "success": result.success,
        "errors":  result.errors,
        "request_summary": getattr(result, "request_summary", ""),
        "artifacts_path": getattr(result, "artifacts_path", ""),
    }
    for agent in ("stack_advisor", "cloud_architect", "infrastructure",
                  "cost_optimization", "security_compliance", "deployment"):
        agent_out = getattr(result, agent, None)
        if agent_out is None:
            continue
        agent_data: dict[str, Any] = {
            "success":  agent_out.success,
            "warnings": agent_out.warnings,
            "errors":   agent_out.errors,
        }
        if hasattr(agent_out, "validated_stack"):
            agent_data["validated_stack"] = agent_out.validated_stack
        if hasattr(agent_out, "total_monthly_usd"):
            agent_data["total_monthly_usd"] = agent_out.total_monthly_usd
            agent_data["total_yearly_usd"]  = agent_out.total_yearly_usd
            agent_data["optimizations"]     = agent_out.optimizations
        if hasattr(agent_out, "compliance_notes"):
            agent_data["compliance_notes"] = agent_out.compliance_notes
            agent_data["rls_policies"]     = agent_out.rls_policies
        if hasattr(agent_out, "pipeline_stages"):
            agent_data["pipeline_stages"] = agent_out.pipeline_stages
        if hasattr(agent_out, "provider"):
            agent_data["provider"] = agent_out.provider
            agent_data["region"]   = agent_out.region
        agent_data["artifact_keys"] = list(agent_out.artifacts.keys()) if agent_out.artifacts else []
        out[agent] = agent_data
    return out


def _build_stack_report(result: dict) -> str:
    """Generate a markdown summary report from a serialized job result."""
    lines: list[str] = ["# DataSphere — Stack Report\n"]

    sa = result.get("stack_advisor") or {}
    stack = sa.get("validated_stack") or {}
    if stack:
        lines.append("## Architecture Summary\n")
        lines.append("| Layer | Tool |")
        lines.append("|-------|------|")
        for layer, tool in stack.items():
            lines.append(f"| {layer} | {tool} |")
        lines.append("")

    co = result.get("cost_optimization") or {}
    if co.get("total_monthly_usd") is not None:
        lines.append("## Cost Estimation\n")
        lines.append(f"- Monthly: **${co['total_monthly_usd']:,.0f}**")
        if co.get("total_yearly_usd") is not None:
            lines.append(f"- Yearly:  **${co['total_yearly_usd']:,.0f}**")
        optimizations = co.get("optimizations") or []
        if optimizations:
            lines.append("\n### Optimizations")
            for opt in optimizations:
                lines.append(f"- {opt}")
        lines.append("")

    sec = result.get("security_compliance") or {}
    compliance_notes = sec.get("compliance_notes") or []
    if compliance_notes:
        lines.append("## Compliance Notes\n")
        for note in compliance_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## Generated Artifact Keys\n")
    for agent_name in ("stack_advisor", "cloud_architect", "infrastructure",
                       "cost_optimization", "security_compliance", "deployment"):
        agent = result.get(agent_name) or {}
        keys = agent.get("artifact_keys") or []
        if keys:
            lines.append(f"### {agent_name}")
            for k in keys:
                lines.append(f"- {k}")
            lines.append("")

    return "\n".join(lines)
