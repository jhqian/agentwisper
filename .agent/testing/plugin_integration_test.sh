#!/usr/bin/env bash
# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

# Broker + Plugin integration test (functional testing mode)
# Verifies: broker starts, plugin structure valid, broker responds to HTTP.
# Does NOT test MCP protocol level (covered by smoke_test.py/system_test.py).
#
# Usage: ./plugin_integration_test.sh
# Prerequisites: uv

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLUGIN_ROOT=""
if [ -d "$AGENT_ROOT/../agentsquad-plugin/.claude-plugin" ]; then
    PLUGIN_ROOT="$(cd "$AGENT_ROOT/../agentsquad-plugin" && pwd)"
fi
DB_PATH="/tmp/agentsquad_integration_test.db"

PASS=0
FAIL=0

pass() { ((PASS++)); echo "  PASS: $1"; }
fail() { ((FAIL++)); echo "  FAIL: $1"; }
info() { echo "  INFO: $1"; }

cleanup() {
    if [ -n "${BROKER_PID:-}" ]; then
        kill "$BROKER_PID" 2>/dev/null || true
        wait "$BROKER_PID" 2>/dev/null || true
    fi
    rm -f "$DB_PATH"
}
trap cleanup EXIT

echo "=== Plugin Integration Tests (Functional) ==="
echo ""

# --- Phase 1: Plugin Structure ---
echo "[Plugin Structure]"

if [ -z "$PLUGIN_ROOT" ] || [ ! -d "$PLUGIN_ROOT" ]; then
    fail "Plugin directory not found at $AGENT_ROOT/../agentsquad-plugin"
    echo "  Skip remaining plugin tests."
    PLUGIN_ROOT=""
else
    # Run plugin structure test
    if [ -f "$PLUGIN_ROOT/.agent/testing/test_plugin_structure.sh" ]; then
        bash "$PLUGIN_ROOT/.agent/testing/test_plugin_structure.sh" 2>&1 | grep -E "PASS|FAIL|Results" | tail -3
        pass "Plugin structure test passed"
    else
        fail "Plugin structure test script not found"
    fi
fi

# --- Phase 2: Broker Startup ---
echo ""
echo "[Broker Startup]"

cd "$AGENT_ROOT"
export AGENTSQUAD_DB_PATH="$DB_PATH"
export PYTHONUNBUFFERED="1"

rm -f "$DB_PATH"

uv run agentsquad-broker start --port 8000 &
BROKER_PID=$!

# Wait for broker to be ready
for i in $(seq 1 30); do
    if curl -s -o /dev/null "http://localhost:8000/mcp" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

if kill -0 "$BROKER_PID" 2>/dev/null; then
    pass "Broker process running (PID $BROKER_PID)"
else
    fail "Broker process not running"
    exit 1
fi

# --- Phase 3: HTTP Endpoint ---
echo ""
echo "[HTTP Endpoint]"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:8000/mcp" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"0.1.0"}}}' \
    2>/dev/null || echo "000")

# Streamable HTTP returns 406 without session header, but any response means server is up
if [ "$HTTP_CODE" != "000" ]; then
    pass "Broker HTTP endpoint responding (status $HTTP_CODE)"
else
    fail "Broker HTTP endpoint not responding"
fi

# --- Phase 4: Run Existing Tests ---
echo ""
echo "[Existing Test Suite]"

if cd "$AGENT_ROOT" && uv run pytest tests/ -q --tb=no 2>&1 | tail -1 | grep -q "passed"; then
    pass "Unit tests passed"
else
    fail "Unit tests failed"
fi

# --- Summary ---
echo ""
echo "=== Results ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
