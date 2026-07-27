# agentsquad

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## Overview

agentsquad is a message broker that lets AI agents coordinate through the Model Context Protocol. Any MCP client — Claude Code, Codex, or a custom agent — registers with the broker, discovers active peers, and exchanges messages with no custom protocol or shared runtime. Agents group into persistent squads with role-based membership for long-running work, or ad-hoc teams for cross-squad tasks, and communicate through direct point-to-point messaging, RPC request/response, or topic-based pub/sub. The broker buffers messages for offline agents and restores identity on reconnect, so an agent can drop and resume without losing state or subscriptions. It runs as a single process backed by SQLite in WAL mode and exposes 26 MCP tools across 6 categories over streamable-http, with no external services or message queues to operate.

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
- **26 MCP Tools** -- agent management, squad operations, ad-hoc teams, messaging, subscriptions, health
- **Communication Patterns** -- P2P direct messaging, RPC request/response, Pub/Sub topic subscriptions
- **Squad Model** -- persistent named groups with role-based membership and shared state
- **Ad-hoc Teams** -- lightweight temporary groups created from multiple squads
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

### Agent Management (5 tools)

| Tool | Description |
|------|-------------|
| `agent_register` | Register a new agent with name and capabilities |
| `agent_deregister` | Remove an agent and clean up its subscriptions |
| `agent_reconnect` | Reconnect a disconnected agent; restores identity, memberships, and buffered messages |
| `agent_list` | List all registered agents |
| `agent_info` | Get detailed information about a specific agent |

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

### Messaging (6 tools)

| Tool | Description |
|------|-------------|
| `message_send` | Send a P2P or RPC message to a specific agent |
| `message_broadcast` | Broadcast a message to topic subscribers |
| `message_poll` | Poll for pending messages |
| `message_wait` | Block until messages arrive (zero-latency via anyio.Event) |
| `message_get` | Retrieve a single message by its msg_id |
| `message_query` | Query message history with filters |

### Subscription (2 tools)

| Tool | Description |
|------|-------------|
| `topic_subscribe` | Subscribe an agent to a topic |
| `topic_unsubscribe` | Unsubscribe from a topic |

### Health (1 tool)

| Tool | Description |
|------|-------------|
| `broker_status` | Get broker health, agent count, queue depth |

## Configuration

Environment variables use the `AGENTSQUAD_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTSQUAD_DB_PATH` | `agentsquad.db` | SQLite database file path |
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
  |                                |<--- message_send() ------------|
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
    broker/              # Registry, managers, router, core
    mcp_server/          # FastMCP tools (26 tools)
    cli/                 # Click CLI entry point
  tests/                 # Test suite (261 tests, incl. 13 integration)
  samples/               # Demo scripts and slash commands
```

## License

Licensed under the [Apache License 2.0](LICENSE).
