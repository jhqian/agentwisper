#!/usr/bin/env bash
# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

# Start the agentsquad broker.
# Usage: ./start_broker.sh [--host <addr>] [--port <port>]
#   --host  Host address to bind (default: 127.0.0.1; use 0.0.0.0 for remote access)
#   --port  HTTP port (default: 8000)
# Press Ctrl+C to stop.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse arguments
BROKER_HOST="127.0.0.1"
BROKER_PORT="8000"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) BROKER_HOST="$2"; shift 2 ;;
        --port) BROKER_PORT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check dependencies
if ! command -v uv &>/dev/null; then
    echo "Error: uv is required. Install from https://docs.astral.sh/uv/"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/pyproject.toml" ]; then
    echo "Error: Cannot find agentsquad project at $PROJECT_ROOT"
    exit 1
fi

echo "Starting agentsquad broker on ${BROKER_HOST}:${BROKER_PORT} ..."
echo "Broker URL: http://${BROKER_HOST}:${BROKER_PORT}/mcp"
echo "Press Ctrl+C to stop."
echo ""
echo "To connect agents, install the agentsquad plugin and run Claude Code:"
echo "  claude plugin add <marketplace>/agentsquad"
echo "  claude"
echo ""
echo "Available commands (type in Claude Code after plugin install):"
echo "  /agentsquad:register <name>   /agentsquad:send <recipient> <msg>"
echo "  /agentsquad:poll [all]         /agentsquad:wait [timeout]"
echo "  /agentsquad:reply <msg_id> <text>"
echo "  /agentsquad:squad <name>      /agentsquad:invite <agent> [role]"
echo "  /agentsquad:broadcast <topic> <msg>"
echo "  /agentsquad:subscribe <topic> /agentsquad:status [agents]"
echo ""

# Clean up any stale DB from previous runs
DB_PATH="/tmp/agentsquad_demo.db"
if [ -f "$DB_PATH" ]; then
    rm "$DB_PATH"
fi

export AGENTSQUAD_DB_PATH="$DB_PATH"
export PYTHONUNBUFFERED="1"

cleanup() {
    if [ -f "$DB_PATH" ]; then
        rm "$DB_PATH"
    fi
    echo ""
    echo "Broker stopped."
}
trap cleanup EXIT

cd "$PROJECT_ROOT"
uv run agentsquad-broker start --port "$BROKER_PORT" --host "$BROKER_HOST"
