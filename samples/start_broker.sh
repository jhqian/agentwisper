#!/usr/bin/env bash
# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

# Start the agentsquad broker.
# Usage: ./start_broker.sh
# Press Ctrl+C to stop.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check dependencies
if ! command -v uv &>/dev/null; then
    echo "Error: uv is required. Install from https://docs.astral.sh/uv/"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/pyproject.toml" ]; then
    echo "Error: Cannot find agentsquad project at $PROJECT_ROOT"
    exit 1
fi

echo "Starting agentsquad broker on port 8000 ..."
echo "Broker URL: http://localhost:8000/mcp"
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
uv run agentsquad-broker start --port 8000
