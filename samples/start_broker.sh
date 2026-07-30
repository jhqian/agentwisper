#!/usr/bin/env bash
# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

# Start the agentwisper broker.
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
    echo "Error: Cannot find agentwisper project at $PROJECT_ROOT"
    exit 1
fi

echo "Starting agentwisper broker on ${BROKER_HOST}:${BROKER_PORT} ..."
echo "Broker URL: http://${BROKER_HOST}:${BROKER_PORT}/mcp"
echo "Press Ctrl+C to stop."
echo ""
echo "To connect agents, install the agentwisper plugin and run Claude Code:"
echo "  claude plugin add <marketplace>/agentwisper"
echo "  claude"
echo ""
echo "Available commands (type in Claude Code after plugin install):"
echo "  /agentwisper:register <name>   /agentwisper:send <recipient> <msg>"
echo "  /agentwisper:poll [all]         /agentwisper:wait [timeout]"
echo "  /agentwisper:squad <name>      /agentwisper:invite <agent> [role]"
echo "  /agentwisper:broadcast <topic> <msg>"
echo "  /agentwisper:subscribe <topic> /agentwisper:status [agents]"
echo ""

# Clean up any stale DB from previous runs
DB_PATH="/tmp/agentwisper_demo.db"
if [ -f "$DB_PATH" ]; then
    rm "$DB_PATH"
fi

export AGENTWHISPER_DB_PATH="$DB_PATH"
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
uv run agentwisper-broker start --port "$BROKER_PORT" --host "$BROKER_HOST"
