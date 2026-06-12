# Changelog

All notable changes to DataSphere are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [Unreleased]

## [1.2.0] - 2026-06-12

### Added
- Stack templates — 10 predefined stacks, `/templates` endpoints, and a UI Templates tab for quick-start configuration
- Enriched interactive CLI — full REPL with `generate`, `diff`, `templates`, `serve`, and `status` commands
- API versioning — `/v1/` URL prefix with deprecation headers on unversioned legacy routes
- Prometheus `/metrics` endpoint — HTTP request counters, job metrics, and latency histograms
- Artifact store — persists generated files and serves them via `/artifacts` endpoints
- Webhook system — register, fire, and retry webhooks with exponential backoff
- Multi-tenant isolation — `X-Tenant-ID` header, per-tenant scoped job store, and per-tenant rate limiting
- Optional OpenTelemetry tracing — OTLP spans emitted per request, agent invocation, and job lifecycle
- Cost optimizer v2 — granular pricing tables, line-item breakdowns, multi-cloud comparison, and savings recommendations
- Stack diff and migration plan generator — `/stacks/diff` endpoint and a UI Migration tab
- Docker integration tests, smoke script, `docker-compose.test.yml`, and a CI integration job
- Data lineage generator with Mermaid diagrams and a `/lineage/generate` endpoint
- Python SDK client `DataSphereClient` with streaming support and a companion CLI
- ZIP export endpoint `GET /jobs/{id}/download` and a UI download button

### Changed
- Raised test coverage floor to 70 %; added README badges and Quick Start guide
- Improved `mode_router` interactive helpers and extended coverage for edge cases

### Fixed
- Set `coverage fail_under` to 70 to match actual measured coverage level

## [1.1.0] - 2026-05-01

### Added
- Production-readiness pass — Redis-backed job store, Helm chart v1.2, full CI/CD pipeline, and UI upgrades
- Production hardening — security headers, structured logging, CORS policy, rate limiting, and Docker hardening
- Terraform generator, SSE streaming endpoint, Bearer-token authentication, and end-to-end tests
- Web UI, SQLite job persistence, Dagster and Prefect generators, and an `upgrade` command
- dbt scaffold generator, Airflow DAG generator, and a FastAPI application layer

### Changed
- Implemented 30 missing adapters across all 12 platform categories

## [1.0.0] - 2026-04-01

### Added
- Initial scaffold — stack-agnostic data platform with 14 configurable layers
- Multi-agent orchestrator with 6 specialised agents
- Stack discovery agent — 10-question context interview before deployment
- 5-step conversational flow letting the user choose their architecture
- Mode 1 (explicit stack selection) and Mode 2 (agent-driven recommendation)

[Unreleased]: https://github.com/datasphere/datasphere/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/datasphere/datasphere/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/datasphere/datasphere/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/datasphere/datasphere/releases/tag/v1.0.0
