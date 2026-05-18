# agentsquad

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Overview

agentsquad is a multi-agent communication platform that provides a central broker for agent coordination, message routing, and team management. It exposes 28 MCP tools across 6 categories through a FastMCP server with streamable-http transport. Agents communicate via P2P messaging, RPC, or Pub/Sub patterns with full SQLite WAL persistence.

## Architecture

```
                    MCP (streamable-http)
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
- **Communication Patterns** -- P2P direct messaging, RPC request/response, Pub/Sub topic subscriptions
- **Squad Model** -- persistent named groups with role-based membership and shared state
- **Ad-hoc Teams** -- lightweight temporary groups created from multiple squads
- **Heartbeat Monitoring** -- automatic agent liveness detection with configurable intervals
- **Message Polling & Wait** -- agents poll or block-wait for messages with `anyio.Event` zero-latency notification
- **Retention Policy** -- automatic cleanup of expired messages and stale agents

## Quick Start

```bash
# Install dependencies
uv sync

# Start the broker on port 8000
uv run agentsquad-broker start
```

For the full walkthrough, see [QUICKSTART.md](QUICKSTART.md).

## Client Configuration

### Claude Code (recommended: plugin)

Install the [agentsquad plugin](https://github.com/jhqian/agentsquad-plugin):

```bash
claude plugin add <marketplace>/agentsquad
```

This provides 10 slash commands (`/agentsquad:register`, `/agentsquad:send`, etc.) and connects to the broker automatically.

### Claude Code (manual HTTP config)

Add to `.claude/settings.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "agentsquad-broker": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Codex

```bash
codex mcp add agentsquad-broker --transport streamable_http --url "http://localhost:8000/mcp"
```

## MCP Tools Reference

### Agent Management (7 tools)

| Tool | Description |
|------|-------------|
| `agent_register` | Register a new agent with name and capabilities |
| `agent_deregister` | Remove an agent and clean up its subscriptions |
| `agent_list` | List all registered agents |
| `agent_info` | Get detailed information about a specific agent |
| `agent_pause` | Pause an agent (buffer messages) |
| `agent_resume` | Resume a paused agent |
| `agent_wake` | Wake a paused agent and optionally inject a message |

### Squad Management (8 tools)

| Tool | Description |
|------|-------------|
| `squad_create` | Create a named squad (creator becomes leader) |
| `squad_dissolve` | Dissolve a squad (leader only) |
| `squad_list` | List all active squads |
| `squad_info` | Get squad details including member list |
| `squad_join` | Add an agent to a squad (leader only) |
| `squad_leave` | Remove an agent from a squad |
| `squad_kick` | Remove a member from squad (leader only) |
| `squad_set_role` | Change a member's role (leader only) |

### Ad-hoc Team (4 tools)

| Tool | Description |
|------|-------------|
| `team_form` | Create a temporary team from agents |
| `team_dismiss` | Dismiss an ad-hoc team |
| `team_list` | List all active ad-hoc teams |
| `team_info` | Get team composition and purpose |

### Messaging (7 tools)

| Tool | Description |
|------|-------------|
| `message_send` | Send a P2P or RPC message to a specific agent |
| `message_broadcast` | Broadcast a message to topic subscribers |
| `message_reply` | Reply to an RPC request |
| `message_poll` | Poll for pending messages |
| `message_wait` | Block until messages arrive (zero-latency via anyio.Event) |
| `message_ack` | Acknowledge message delivery |
| `message_query` | Query message history with filters |

### Subscription (2 tools)

| Tool | Description |
|------|-------------|
| `topic_subscribe` | Subscribe an agent to a topic |
| `topic_unsubscribe` | Unsubscribe from a topic |

### Health (2 tools)

| Tool | Description |
|------|-------------|
| `heartbeat` | Signal agent is alive |
| `broker_status` | Get broker health, agent count, queue depth |

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
| `AGENTSQUAD_HTTP_PORT` | `8000` | Port for streamable-http transport |

## Communication Patterns

### P2P (Point-to-Point)

Direct message from one agent to another. Best for targeted requests and responses.

```
Agent A                          Broker                          Agent B
  |                                |                                |
  |--- message_send(to=B) ------->|                                |
  |                                |-- store message -------------->|
  |                                |                                |
  |                                |<-------- message_poll() -------|
  |                                |--- deliver message ----------->|
  |                                |                                |
```

### RPC (Request-Response)

Synchronous request/response with timeout. Caller blocks until responder replies.

```
Agent A                          Broker                          Agent B
  |                                |                                |
  |--- message_send(type=rpc) ---->|                                |
  |                                |-- store RPC request ----------->|
  |                                |                                |
  |                                |<--- message_poll() -------------|
  |                                |--- deliver request ----------->|
  |                                |                                |
  |                                |<--- message_reply() -----------|
  |<-- RPC response ---------------|                                |
  |                                |                                |
```

### Pub/Sub (Publish-Subscribe)

Topic-based broadcasting. Subscribers receive messages posted to topics they follow.

```
Publisher                        Broker                          Subscriber
  |                                |                                |
  |--- message_broadcast(topic=X)->|                                |
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
| Creation | `squad_create` | `team_form` |
| Membership | Agents join/leave | Specified at creation |
| Roles | Per-member roles | Flat membership |
| Communication | Broadcast to squad | Broadcast to team |
| Use case | Long-running teams, departments | Task forces, cross-squad projects |
| Cleanup | Explicit `squad_dissolve` | Explicit `team_dismiss` |

## Development

```bash
# Run all tests
uv run pytest

# Run specific test layer
uv run pytest tests/test_broker/

# Smoke test (MCP client integration)
uv run python tests/smoke_test.py

# System test (lifecycle & messaging)
uv run python tests/system_test.py
```

### Project Structure

```
agentsquad/
  src/
    common/              # Types, config
    persistence/         # Database, stores
    broker/              # Registry, managers, router, heartbeat, core
    mcp_server/          # FastMCP tools (28 tools)
    cli/                 # Click CLI entry point
  tests/                 # Test suite (182 unit tests)
  samples/               # Demo scripts and slash commands
```

## License

Licensed under the [Apache License 2.0](LICENSE).
