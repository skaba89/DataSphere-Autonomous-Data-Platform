"""ARQ worker — optional async task queue for DataSphere generation jobs.

When ``DATASPHERE_REDIS_URL`` is set and ``arq`` is installed, generation jobs
are enqueued in Redis instead of running in-process via FastAPI BackgroundTasks.

Run the worker standalone::

    python -m datasphere.api.worker

Or via arq CLI::

    arq datasphere.api.worker.WorkerSettings
"""
from __future__ import annotations

import os
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Optional arq import — gracefully degrade if not installed
# ---------------------------------------------------------------------------
try:
    import arq
    from arq import create_pool
    from arq.connections import RedisSettings, ArqRedis
    _ARQ_AVAILABLE = True
except ImportError:  # pragma: no cover
    arq = None  # type: ignore[assignment]
    _ARQ_AVAILABLE = False

_REDIS_URL: Optional[str] = os.environ.get("DATASPHERE_REDIS_URL", "")


# ---------------------------------------------------------------------------
# ARQ job function
# ---------------------------------------------------------------------------

async def run_generation_job(ctx: dict, job_id: str, req_dict: dict) -> None:  # noqa: ARG001
    """ARQ job function — deserialises the request dict and runs generation.

    ``ctx`` is the ARQ worker context (contains the Redis pool, etc.).
    ``job_id`` is the DataSphere job ID (already stored in the job store).
    ``req_dict`` is the serialised ``GenerateRequest`` as a plain dict.
    """
    # Import here to avoid circular imports at module load time.
    from datasphere.api.app import GenerateRequest, _run_generation  # noqa: PLC0415

    req = GenerateRequest(**req_dict)
    # _run_generation is synchronous; run it in the default executor so we
    # don't block the event loop inside the ARQ worker.
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_generation, job_id, req)


# ---------------------------------------------------------------------------
# WorkerSettings
# ---------------------------------------------------------------------------

def _redis_settings_from_env() -> "RedisSettings":
    """Build arq RedisSettings from DATASPHERE_REDIS_URL."""
    url = _REDIS_URL or "redis://localhost:6379"
    return RedisSettings.from_dsn(url)


class WorkerSettings:
    """ARQ WorkerSettings — pass to ``arq`` CLI or ``arq.Worker``."""

    functions = [run_generation_job]

    @property
    def redis_settings(self) -> "RedisSettings":  # type: ignore[return]
        return _redis_settings_from_env()


# ---------------------------------------------------------------------------
# Helper used by app.py
# ---------------------------------------------------------------------------

async def enqueue_generation(job_id: str, req_dict: dict) -> Optional[Any]:
    """Enqueue a generation job in ARQ if Redis is configured.

    Returns the arq Job object when successfully enqueued, or ``None`` when
    ARQ / Redis is not available (caller should fall back to BackgroundTasks).
    """
    if not _ARQ_AVAILABLE:
        return None
    if not _REDIS_URL:
        return None
    try:
        pool: ArqRedis = await create_pool(_redis_settings_from_env())
        job = await pool.enqueue_job("run_generation_job", job_id, req_dict)
        await pool.aclose()
        return job
    except Exception:  # pragma: no cover — Redis unreachable at runtime
        return None


# ---------------------------------------------------------------------------
# Standalone entry-point: python -m datasphere.api.worker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not _ARQ_AVAILABLE:
        raise SystemExit(
            "arq is not installed. Install it with: pip install 'arq>=0.25'"
        )
    if not _REDIS_URL:
        raise SystemExit(
            "DATASPHERE_REDIS_URL is not set. "
            "Set it to a Redis DSN, e.g. redis://localhost:6379"
        )
    import asyncio
    from arq import Worker

    async def _main() -> None:
        worker = Worker(
            functions=[run_generation_job],
            redis_settings=_redis_settings_from_env(),
        )
        await worker.async_run()

    asyncio.run(_main())
