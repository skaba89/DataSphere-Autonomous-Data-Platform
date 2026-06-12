#!/usr/bin/env bash
# Smoke test script for the DataSphere API.
# Usage: ./scripts/smoke_test.sh [BASE_URL]
# Default BASE_URL: http://localhost:8000

set -euo pipefail

BASE_URL="${1:-${DATASPHERE_BASE_URL:-http://localhost:8000}}"

# Color support
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  RED='\033[0;31m'
  RESET='\033[0m'
else
  GREEN=''
  RED=''
  RESET=''
fi

PASS=0
FAIL=0

pass() { echo -e "${GREEN}PASS${RESET} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}FAIL${RESET} $1"; FAIL=$((FAIL + 1)); }

check_status() {
  local label="$1"
  local url="$2"
  local method="${3:-GET}"
  local body="${4:-}"
  local expected_key="${5:-}"

  if [ "$method" = "POST" ]; then
    response=$(curl -sf -X POST "$url" \
      -H "Content-Type: application/json" \
      -d "$body" 2>/dev/null) && status=0 || status=$?
  else
    response=$(curl -sf "$url" 2>/dev/null) && status=0 || status=$?
  fi

  if [ $status -ne 0 ]; then
    fail "$label — HTTP request failed (curl exit $status)"
    return
  fi

  if [ -n "$expected_key" ]; then
    if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$expected_key' in d" 2>/dev/null; then
      pass "$label"
    else
      fail "$label — response missing key '$expected_key': $response"
    fi
  else
    pass "$label"
  fi
}

echo "Smoke testing DataSphere API at $BASE_URL"
echo "-------------------------------------------"

# GET /healthz → 200
check_status "GET /healthz" "${BASE_URL}/healthz"

# GET /readyz → 200
check_status "GET /readyz" "${BASE_URL}/readyz"

# GET / → JSON with "name" key
check_status "GET / (name key)" "${BASE_URL}/" "GET" "" "name"

# POST /generate/sync with minimal payload
GENERATE_PAYLOAD='{"source":"snowflake","orchestrator":"airflow","infrastructure":"aws"}'
check_status "POST /generate/sync" "${BASE_URL}/generate/sync" "POST" "$GENERATE_PAYLOAD"

# POST /dbt/generate → 200 with file_count
DBT_PAYLOAD='{"source":"snowflake","project_name":"smoke_test"}'
check_status "POST /dbt/generate (file_count)" "${BASE_URL}/dbt/generate" "POST" "$DBT_PAYLOAD" "file_count"

# POST /terraform/generate → 200 with file_count
TF_PAYLOAD='{"infrastructure":"aws","project_name":"smoke_test"}'
check_status "POST /terraform/generate (file_count)" "${BASE_URL}/terraform/generate" "POST" "$TF_PAYLOAD" "file_count"

# GET /stacks/supported → 200
check_status "GET /stacks/supported" "${BASE_URL}/stacks/supported"

# GET /jobs → 200 (JSON array)
jobs_response=$(curl -sf "${BASE_URL}/jobs" 2>/dev/null) && jobs_status=0 || jobs_status=$?
if [ $jobs_status -ne 0 ]; then
  fail "GET /jobs — HTTP request failed"
elif echo "$jobs_response" | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d,list)" 2>/dev/null; then
  pass "GET /jobs (array)"
else
  fail "GET /jobs — expected JSON array, got: $jobs_response"
fi

echo "-------------------------------------------"
echo "Results: ${GREEN}${PASS} passed${RESET}, ${RED}${FAIL} failed${RESET}"

if [ $FAIL -gt 0 ]; then
  exit 1
fi
