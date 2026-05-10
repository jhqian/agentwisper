# Vibe AgentSquad

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Overview

Vibe AgentSquad is a multi-agent communication platform that provides a central broker for agent coordination, message routing, and team management. It exposes 28 MCP tools across 6 categories through a FastMCP server interface, supporting both stdio and HTTP transports. Agents communicate via P2P messaging, RPC, or Pub/Sub patterns with full SQLite WAL persistence.

## Architecture

```
                    MCP (stdio/SSE/HTTP)
                         |
                    +----+----+
                    |   MCP   |
                    |  Server |
                    +----+----+
                         |
+------------------------+------------------------+
|                  Broker Core                      |
|  +----------+ +-----------+ +----------------+   |
|  |  Router  | |   Agent   | |     Squad      |   |
|  | P2P/RPC/ | | Registry  | |   Manager      |   |
|  |  PubSub  | |           | |                |   |
|  +----+-----+ +-----+-----+ +------+---------+   |
|       +--------------+------+                   |
|              +-------+--------+                  |
|              | Heartbeat     |                   |
|              | Monitor       |                   |
|              +---------------+                   |
|                                                   |
|  +---------------------------------------------+ |
|  |        Persistence Layer (SQLite WAL)        | |
|  |  messages | agents | squads | subscriptions | |
|  +---------------------------------------------+ |
+---------------------------------------------------+
         |              |              |
    Claude Code      Codex       Custom Agent
```

## Features

- **Central Broker** -- single-process message broker with SQLite WAL persistence
- **28 MCP Tools** -- agent management, squad operations, ad-hoc teams, messaging, subscriptions, health
- **Multiple Transports** -- stdio, SSE, and streamable HTTP via FastMCP
- **Communication Patterns** -- P2P direct messaging, RPC request/response, Pub/Sub topic subscriptions
- **Squad Model** -- persistent named groups with role-based membership and shared state
- **Ad-hoc Teams** -- lightweight temporary groups created from multiple squads
- **Heartbeat Monitoring** -- automatic agent liveness detection with configurable intervals
- **Message Polling** -- agents pull messages at their own pace with configurable batch sizes
- **Retention Policy** -- automatic cleanup of expired messages and stale agents

## Quick Start

```bash
# Install dependencies
uv sync

# Start the broker (stdio mode, default)
uv run vibe-broker start

# Start the broker (HTTP mode)
AGENTSQUAD_TRANSPORT=http uv run vibe-broker start
```

See [QUICKSTART.md](QUICKSTART.md) for the full walkthrough.

## Client Configuration

### Transport Comparison

| Transport | Protocol | Best For | Multi-Client |
|-----------|----------|----------|:------------:|
| stdio | stdin/stdout | Single agent, local dev | No |
| SSE | HTTP + Server-Sent Events | Web dashboards, browsers | Yes |
| HTTP | HTTP POST | Multi-agent, production | Yes |

### Claude Code

Stdio (add to `.claude/settings.json`):

```json
{
  "mcpServers": {
    "vibe-broker": {
      "command": "uv",
      "args": ["run", "vibe-broker", "start"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

HTTP (add to `.claude/settings.json`):

```json
{
  "mcpServers": {
    "vibe-broker": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### OpenCode

Stdio (add to OpenCode config):

```json
{
  "mcp": {
    "vibe-broker": {
      "type": "local",
      "command": ["uv", "run", "vibe-broker", "start"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

HTTP (add to OpenCode config):

```json
{
  "mcp": {
    "vibe-broker": {
      "type": "remote",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Codex

Stdio:

```bash
codex mcp add vibe-broker --transport stdio --command "uv run vibe-broker start"
```

HTTP:

```bash
codex mcp add vibe-broker --transport streamable_http --url "http://localhost:8000/mcp"
```

## MCP Tools Reference

### Agent Management (6 tools)

| Tool | Description |
|------|-------------|
| `register_agent` | Register a new agent with name, description, and capabilities |
| `deregister_agent` | Remove an agent and clean up its subscriptions |
| `list_agents` | List all registered agents with optional status filtering |
| `get_agent_info` | Get detailed information about a specific agent |
| `agent_heartbeat` | Send a heartbeat signal to maintain agent liveness |
| `update_agent` | Update agent metadata (description, capabilities, status) |

### Squad Management (8 tools)

| Tool | Description |
|------|-------------|
| `create_squad` | Create a named squad with description and configuration |
| `dissolve_squad` | Dissolve a squad and remove all memberships |
| `list_squads` | List all squads with optional filtering |
| `get_squad_info` | Get squad details including member list |
| `join_squad` | Add an agent to a squad with an optional role |
| `leave_squad` | Remove an agent from a squad |
| `update_squad` | Update squad metadata (name, description, configuration) |
| `list_squad_members` | List all members of a specific squad with roles |

### Ad-hoc Team (4 tools)

| Tool | Description |
|------|-------------|
| `form_team` | Create a temporary team from agents across multiple squads |
| `disband_team` | Disband an ad-hoc team |
| `list_teams` | List all active ad-hoc teams |
| `get_team_info` | Get team composition and purpose |

### Messaging (6 tools)

| Tool | Description |
|------|-------------|
| `send_message` | Send a P2P message to a specific agent |
| `broadcast_to_squad` | Broadcast a message to all members of a squad |
| `call_agent` | Send an RPC request and wait for a response |
| `respond_to_call` | Respond to a pending RPC request |
| `poll_messages` | Poll for pending messages (P2P, RPC, broadcast) |
| `get_message_history` | Retrieve message history with optional filtering |

### Subscription (2 tools)

| Tool | Description |
|------|-------------|
| `subscribe` | Subscribe an agent to a topic for Pub/Sub messaging |
| `unsubscribe` | Unsubscribe an agent from a topic |

### Health (2 tools)

| Tool | Description |
|------|-------------|
| `health_check` | Get broker health status including uptime and statistics |
| `ping` | Lightweight liveness check |

## Configuration

Environment variables use the `AGENTSQUAD_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSQUAD_DB_PATH` | `agentsquad.db` | SQLite database file path |
| `AGENTSQUAD_HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeat checks |
| `AGENTSQUAD_HEARTBEAT_TIMEOUT` | `90` | Seconds before agent marked offline |
| `AGENTSQUAD_RPC_TIMEOUT` | `30` | Seconds to wait for RPC response |
| `AGENTSQUAD_POLL_LIMIT` | `50` | Max messages returned per poll call |
| `AGENTSQUAD_RETENTION_DAYS` | `30` | Days to retain messages before cleanup |
| `AGENTSQUAD_TRANSPORT` | `stdio` | Transport mode: `stdio`, `sse`, or `http` |
| `AGENTSQUAD_HTTP_PORT` | `8000` | Port for HTTP/SSE transport |

## Communication Patterns

### P2P (Point-to-Point)

Direct message from one agent to another. Best for targeted requests and responses.

```
Agent A                          Broker                          Agent B
  |                                |                                |
  |--- send_message(to=B) -------->|                                |
  |                                |-- store message -------------->|
  |                                |                                |
  |                                |<-------- poll_messages() ------|
  |                                |--- deliver message ----------->|
  |                                |                                |
```

### RPC (Request-Response)

Synchronous request/response with timeout. Caller blocks until responder replies.

```
Agent A                          Broker                          Agent B
  |                                |                                |
  |--- call_agent(target=B) ------>|                                |
  |    (blocks until response)     |-- store RPC request ----------->|
  |                                |                                |
  |                                |<--- poll_messages() ------------|
  |                                |--- deliver request ----------->|
  |                                |                                |
  |                                |<--- respond_to_call() ---------|
  |<-- RPC response ---------------|                                |
  |                                |                                |
```

### Pub/Sub (Publish-Subscribe)

Topic-based broadcasting. Subscribers receive messages posted to topics they follow.

```
Publisher                        Broker                          Subscriber
  |                                |                                |
  |--- send_message(topic=X) ----->|                                |
  |                                |-- lookup subscribers --------->|
  |                                |                                |
  |                                |       Subscriber A             Subscriber B
  |                                |-- deliver --------->|          |<-- deliver
  |                                |                                |
```

## Squad and Team Model

| Aspect | Squad | Ad-hoc Team |
|--------|-------|-------------|
| Lifetime | Persistent | Temporary |
| Creation | `create_squad` | `form_team` |
| Membership | Agents join/leave | Specified at creation |
| Roles | Per-member roles | Flat membership |
| Communication | Broadcast to squad | Broadcast to team |
| Use case | Long-running teams, departments | Task forces, cross-squad projects |
| Cleanup | Explicit `dissolve_squad` | Explicit `disband_team` |

## Development

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Run specific test file
uv run pytest tests/test_broker.py

# Lint
uv run ruff check src/
uv run mypy src/
```

### Project Structure

```
agentsquad/
  src/
    agentsquad/
      broker/          # Broker core (router, registry, manager)
      mcp/             # MCP server and tool definitions
      db/              # SQLite persistence layer
      models/          # Data models and types
  tests/               # Test suite
```

## License

Licensed under the [Apache License 2.0](LICENSE).
