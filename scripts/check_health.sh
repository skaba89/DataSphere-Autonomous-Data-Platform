#!/bin/bash
BASE_URL="${1:-http://localhost:8000}"

echo "=== DataSphere Health Check: $BASE_URL ==="

check() {
    local name="$1"
    local url="$2"
    local expected="$3"

    response=$(curl -sf "$url" 2>/dev/null)
    if [ $? -eq 0 ]; then
        if echo "$response" | grep -q "$expected" 2>/dev/null; then
            echo "  ✓ $name"
        else
            echo "  ⚠ $name (unexpected response)"
        fi
    else
        echo "  ✗ $name (failed)"
        return 1
    fi
}

check "Liveness (/healthz)"  "$BASE_URL/healthz" '"status"'
check "Readiness (/readyz)"  "$BASE_URL/readyz"  '"status"'
check "Metrics (/metrics)"   "$BASE_URL/metrics" 'datasphere_up'
check "Templates"            "$BASE_URL/templates" '"count"'
check "Plugins"              "$BASE_URL/plugins" '"count"'
check "Jobs"                 "$BASE_URL/jobs" '['

echo ""
echo "Health check complete."
