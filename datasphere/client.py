"""
DataSphere Python SDK client.

Usage:
    from datasphere.client import DataSphereClient

    client = DataSphereClient("http://localhost:8000", api_key="optional")

    # Synchronous generation
    result = client.generate(
        business_request="Pipeline analytics ventes",
        cloud_provider="aws",
        data_warehouse="snowflake",
        orchestrator="airflow",
        ingestion="airbyte",
        transformation="dbt",
        bi_tool="metabase",
        deployment="kubernetes",
        budget="medium",
    )

    # Async streaming generation
    for event in client.stream(
        business_request="...",
        cloud_provider="aws",
        ...
    ):
        print(event)  # dict with type/message/result

    # Generator-specific methods
    result = client.generate_dbt(business_request="...", data_warehouse="snowflake")
    result = client.generate_terraform(business_request="...", cloud_provider="aws", ...)
    result = client.download_job(job_id, output_dir="./output")  # saves ZIP to disk
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Iterator

# ---------------------------------------------------------------------------
# HTTP backend — prefer httpx if available, fall back to urllib
# ---------------------------------------------------------------------------
try:
    import httpx as _httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

if not _HTTPX_AVAILABLE:
    import urllib.request
    import urllib.error


class DataSphereError(Exception):
    """Raised when the DataSphere API returns an error."""


class DataSphereClient:
    """Minimal Python client for the DataSphere API."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 120,
        api_version: str = "v1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._version_prefix = f"/{api_version}" if api_version else ""

    # ------------------------------------------------------------------
    # Private HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{self._version_prefix}{path}"
        body = json.dumps(payload).encode()
        if _HTTPX_AVAILABLE:
            with _httpx.Client(timeout=self.timeout) as c:
                resp = c.post(url, content=body, headers=self._headers())
            if resp.status_code >= 400:
                raise DataSphereError(f"POST {path} → {resp.status_code}: {resp.text}")
            return resp.json()
        else:
            req = urllib.request.Request(
                url, data=body, headers=self._headers(), method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                raise DataSphereError(
                    f"POST {path} → {exc.code}: {exc.read().decode()}"
                ) from exc

    def _get(self, path: str) -> dict | bytes:
        url = f"{self.base_url}{self._version_prefix}{path}"
        if _HTTPX_AVAILABLE:
            with _httpx.Client(timeout=self.timeout) as c:
                resp = c.get(url, headers=self._headers())
            if resp.status_code >= 400:
                raise DataSphereError(f"GET {path} → {resp.status_code}: {resp.text}")
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                return resp.json()
            return resp.content
        else:
            req = urllib.request.Request(url, headers=self._headers(), method="GET")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    ct = resp.headers.get("Content-Type", "")
                    raw = resp.read()
                    if "json" in ct:
                        return json.loads(raw)
                    return raw
            except urllib.error.HTTPError as exc:
                raise DataSphereError(
                    f"GET {path} → {exc.code}: {exc.read().decode()}"
                ) from exc

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def health(self) -> dict:
        """GET /healthz — liveness probe."""
        return self._get("/healthz")  # type: ignore[return-value]

    def generate(
        self,
        business_request: str,
        cloud_provider: str,
        data_warehouse: str,
        orchestrator: str = "airflow",
        ingestion: str = "airbyte",
        transformation: str = "dbt",
        bi_tool: str = "metabase",
        deployment: str = "docker-compose",
        budget: str = "medium",
        security: str | None = None,
        mode: str = "explicit",
    ) -> dict:
        """POST /generate/sync — synchronous generation, returns result dict."""
        payload: dict = {
            "business_request": business_request,
            "cloud_provider": cloud_provider,
            "data_warehouse": data_warehouse,
            "orchestrator": orchestrator,
            "ingestion": ingestion,
            "transformation": transformation,
            "bi_tool": bi_tool,
            "deployment": deployment,
            "budget": budget,
            "mode": mode,
        }
        if security is not None:
            payload["security"] = security
        return self._post("/generate/sync", payload)

    def generate_async(
        self,
        business_request: str,
        cloud_provider: str,
        data_warehouse: str,
        orchestrator: str = "airflow",
        ingestion: str = "airbyte",
        transformation: str = "dbt",
        bi_tool: str = "metabase",
        deployment: str = "docker-compose",
        budget: str = "medium",
        security: str | None = None,
        mode: str = "explicit",
    ) -> str:
        """POST /generate — async, returns job_id."""
        payload: dict = {
            "business_request": business_request,
            "cloud_provider": cloud_provider,
            "data_warehouse": data_warehouse,
            "orchestrator": orchestrator,
            "ingestion": ingestion,
            "transformation": transformation,
            "bi_tool": bi_tool,
            "deployment": deployment,
            "budget": budget,
            "mode": mode,
        }
        if security is not None:
            payload["security"] = security
        result = self._post("/generate", payload)
        return result["job_id"]

    def get_job(self, job_id: str) -> dict:
        """GET /jobs/{job_id} — fetch job status."""
        return self._get(f"/jobs/{job_id}")  # type: ignore[return-value]

    def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> dict:
        """Poll GET /jobs/{job_id} until status is completed or failed."""
        deadline = time.monotonic() + timeout
        while True:
            job = self.get_job(job_id)
            status = job.get("status", "")
            if status in ("completed", "failed"):
                return job
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Job {job_id} did not finish within {timeout}s (last status: {status})"
                )
            time.sleep(poll_interval)

    def stream(
        self,
        business_request: str,
        cloud_provider: str,
        data_warehouse: str,
        orchestrator: str = "airflow",
        ingestion: str = "airbyte",
        transformation: str = "dbt",
        bi_tool: str = "metabase",
        deployment: str = "docker-compose",
        budget: str = "medium",
        security: str | None = None,
        mode: str = "explicit",
    ) -> Iterator[dict]:
        """
        Start an async job, then stream SSE events from GET /generate/stream?job_id=...

        Yields dicts parsed from `data: {...}` SSE lines.
        """
        job_id = self.generate_async(
            business_request=business_request,
            cloud_provider=cloud_provider,
            data_warehouse=data_warehouse,
            orchestrator=orchestrator,
            ingestion=ingestion,
            transformation=transformation,
            bi_tool=bi_tool,
            deployment=deployment,
            budget=budget,
            security=security,
            mode=mode,
        )
        url = f"{self.base_url}/generate/stream?job_id={job_id}"
        yield from self._stream_sse(url)

    def _stream_sse(self, url: str) -> Iterator[dict]:
        """Read SSE from *url* and yield parsed data dicts."""
        headers = {k: v for k, v in self._headers().items() if k != "Content-Type"}
        headers["Accept"] = "text/event-stream"

        if _HTTPX_AVAILABLE:
            with _httpx.Client(timeout=self.timeout) as c:
                with c.stream("GET", url, headers=headers) as resp:
                    for line in resp.iter_lines():
                        event = self._parse_sse_line(line)
                        if event is not None:
                            yield event
                            if event.get("type") in ("completed", "failed", "done"):
                                return
        else:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").rstrip("\n\r")
                    event = self._parse_sse_line(line)
                    if event is not None:
                        yield event
                        if event.get("type") in ("completed", "failed", "done"):
                            return

    @staticmethod
    def _parse_sse_line(line: str) -> dict | None:
        if line.startswith("data:"):
            data = line[5:].strip()
            if data:
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return {"type": "raw", "message": data}
        return None

    def generate_dbt(
        self,
        business_request: str,
        data_warehouse: str = "snowflake",
        ingestion: str = "airbyte",
    ) -> dict:
        """POST /dbt/generate — generate dbt project scaffold."""
        return self._post(
            "/dbt/generate",
            {
                "business_request": business_request,
                "data_warehouse": data_warehouse,
                "ingestion": ingestion,
            },
        )

    def generate_airflow(
        self,
        business_request: str,
        ingestion: str = "airbyte",
        transformation: str = "dbt",
        quality: str = "great-expectations",
        processing_mode: str = "batch",
    ) -> dict:
        """POST /dags/airflow/generate — generate Airflow DAGs."""
        return self._post(
            "/dags/airflow/generate",
            {
                "business_request": business_request,
                "ingestion": ingestion,
                "transformation": transformation,
                "quality": quality,
                "processing_mode": processing_mode,
            },
        )

    def generate_dagster(
        self,
        business_request: str,
        data_warehouse: str = "snowflake",
        ingestion: str = "airbyte",
    ) -> dict:
        """POST /dagster/generate — generate Dagster project."""
        return self._post(
            "/dagster/generate",
            {
                "business_request": business_request,
                "data_warehouse": data_warehouse,
                "ingestion": ingestion,
            },
        )

    def generate_prefect(
        self,
        business_request: str,
        data_warehouse: str = "snowflake",
        ingestion: str = "airbyte",
    ) -> dict:
        """POST /prefect/generate — generate Prefect flows."""
        return self._post(
            "/prefect/generate",
            {
                "business_request": business_request,
                "data_warehouse": data_warehouse,
                "ingestion": ingestion,
            },
        )

    def generate_terraform(
        self,
        business_request: str,
        cloud_provider: str = "aws",
        data_warehouse: str = "snowflake",
        deployment: str = "kubernetes",
        budget: str = "medium",
    ) -> dict:
        """POST /terraform/generate — generate Terraform IaC."""
        return self._post(
            "/terraform/generate",
            {
                "business_request": business_request,
                "cloud_provider": cloud_provider,
                "data_warehouse": data_warehouse,
                "deployment": deployment,
                "budget": budget,
            },
        )

    def download_job(self, job_id: str, output_dir: str = ".") -> str:
        """GET /jobs/{job_id}/download — save ZIP artifact, return file path."""
        raw = self._get(f"/jobs/{job_id}/download")
        if isinstance(raw, dict):
            # API returned JSON (e.g. error or redirect info)
            raise DataSphereError(f"Expected binary ZIP, got JSON: {raw}")
        os.makedirs(output_dir, exist_ok=True)
        dest = os.path.join(output_dir, f"{job_id}.zip")
        with open(dest, "wb") as fh:
            fh.write(raw)  # type: ignore[arg-type]
        return dest

    def list_jobs(self) -> list[dict]:
        """GET /jobs — list all jobs."""
        result = self._get("/jobs")
        if isinstance(result, list):
            return result
        # API may wrap in {"jobs": [...]}
        if isinstance(result, dict):
            return result.get("jobs", result.get("items", []))
        return []


# ---------------------------------------------------------------------------
# Minimal CLI
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    """Entry point for `datasphere-client` command."""
    parser = argparse.ArgumentParser(
        prog="datasphere-client",
        description="DataSphere SDK CLI",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("DATASPHERE_URL", "http://localhost:8000"),
        help="Base URL of the DataSphere API (env: DATASPHERE_URL)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("DATASPHERE_API_KEY"),
        help="API key (env: DATASPHERE_API_KEY)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # health
    subparsers.add_parser("health", help="Check API health")

    # generate
    gen_p = subparsers.add_parser("generate", help="Generate a data platform")
    gen_p.add_argument("business_request", help="Business use-case description")
    gen_p.add_argument("--cloud", default="aws", help="Cloud provider (default: aws)")
    gen_p.add_argument(
        "--warehouse", default="snowflake", help="Data warehouse (default: snowflake)"
    )
    gen_p.add_argument("--orchestrator", default="airflow")
    gen_p.add_argument("--ingestion", default="airbyte")
    gen_p.add_argument("--transformation", default="dbt")
    gen_p.add_argument("--bi-tool", default="metabase")
    gen_p.add_argument("--deployment", default="docker-compose")
    gen_p.add_argument("--budget", default="medium")
    gen_p.add_argument("--mode", default="explicit")

    # jobs
    subparsers.add_parser("jobs", help="List all jobs")

    args = parser.parse_args()
    client = DataSphereClient(args.url, api_key=args.api_key)

    if args.command == "health":
        result = client.health()
        print(json.dumps(result, indent=2))

    elif args.command == "generate":
        result = client.generate(
            business_request=args.business_request,
            cloud_provider=args.cloud,
            data_warehouse=args.warehouse,
            orchestrator=args.orchestrator,
            ingestion=args.ingestion,
            transformation=args.transformation,
            bi_tool=args.bi_tool,
            deployment=args.deployment,
            budget=args.budget,
            mode=args.mode,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "jobs":
        jobs = client.list_jobs()
        print(json.dumps(jobs, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli_main()
