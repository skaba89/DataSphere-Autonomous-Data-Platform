# DataSphere Load Tests

## Prerequisites
- Running DataSphere API: `uvicorn datasphere.api.app:app --port 8000`

## Locust (Python)
pip install locust
locust -f load_tests/locustfile.py --host http://localhost:8000
# Open http://localhost:8089 for the web UI

# Headless (CI):
locust -f load_tests/locustfile.py --host http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 60s --headless

## k6 (Go binary)
# Install: https://k6.io/docs/getting-started/installation/
k6 run load_tests/k6_script.js
k6 run --vus 50 --duration 60s load_tests/k6_script.js

## Interpreting results
- p95 < 2000ms = good
- error rate < 5% = acceptable
- error rate < 1% = target
