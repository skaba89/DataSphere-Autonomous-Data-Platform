# ---- build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ".[api]" --target /deps

# ---- runtime stage ----
FROM python:3.11-slim AS runtime

# Non-root user
RUN groupadd -r datasphere && useradd -r -g datasphere -d /app -s /sbin/nologin datasphere

WORKDIR /app

# Copy installed packages
COPY --from=builder /deps /usr/local/lib/python3.11/site-packages/

# Copy application source
COPY --chown=datasphere:datasphere datasphere/ ./datasphere/

# Writable directory for SQLite job store
RUN mkdir -p /data && chown datasphere:datasphere /data

USER datasphere

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATASPHERE_JOB_DB=/data/jobs.db \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/readyz')" || exit 1

CMD ["python", "-m", "uvicorn", "datasphere.api.app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", \
     "--timeout-graceful-shutdown", "30"]
