<!-- Copyright 2026 vibe-agentsquad contributors, Licensed under the Apache License, Version 2.0 -->

# Quick Start Guide

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Required |
| [uv](https://docs.astral.sh/uv/) | Latest | Package manager |
| MCP-compatible client | Any | Claude Code, OpenCode, Codex, or custom |

## Installation

```bash
git clone <repo-url> agentsquad
cd agentsquad
uv sync
```

Verify the installation by collecting tests:

```bash
uv run pytest --co -q
# 152 tests collected
```

## Choosing a Transport

| Transport | Protocol | Best For | Multi-Client | Latency |
|-----------|----------|----------|:------------:|---------|
| `stdio` | stdin/stdout | Single agent, local dev | No | Lowest |
| `streamable-http` | HTTP POST | Multi-agent, production | Yes | Low |
| `sse` | HTTP + Server-Sent Events | Web dashboards, browsers | Yes | Low |

## Single-Agent Setup (stdio)

The simplest configuration -- one agent connected via stdio.

**1. Configure Claude Code** (`.claude/settings.json`):

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

The `PYTHONUNBUFFERED=1` env var ensures broker logs flush immediately.

**2. Verify connection** by calling `broker_status`:

```json
{
  "status": "ok",
  "agents": 0,
  "pending_messages": 0
}
```

**3. Register an agent**:

```json
// agent_register(name="agent_a", capabilities=["code-review", "testing"])
{
  "agent_id": "a1b2c3d4",
  "name": "agent_a",
  "status": "active"
}
```

## Multi-Agent Setup (streamable-http)

Multiple agents connect to a single broker over HTTP.

**1. Start the broker**:

```bash
uv run vibe-broker start --transport streamable-http --port 8000
```

The broker binds to `http://localhost:8000/mcp`.

**2. Configure clients**:

Claude Code (`.claude/settings.json`):

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

OpenCode (OpenCode config):

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

Codex:

```bash
codex mcp add vibe-broker --transport streamable_http --url "http://localhost:8000/mcp"
```

**3. Register agents** from each client:

```json
// Client A: agent_register(name="agent_a", capabilities=["code-review"])
// Client B: agent_register(name="agent_b", capabilities=["testing"])
// Client C: agent_register(name="agent_c", capabilities=["docs"])
```

## Common Workflows

### P2P Messaging

Send a direct message from one agent to another.

```json
// agent_a sends to agent_b
message_send(
  sender_id="a1b2c3d4",
  recipient="agent_b",
  payload="\"Please review PR #42\"",
  msg_type="p2p"
)
// => {"msg_id": "m1", "status": "pending"}

// agent_b polls for messages
message_poll(agent_id="e5f6g7h8")
// => {"messages": [{"msg_id": "m1", "sender_id": "a1b2c3d4", "payload": "Please review PR #42"}], "total": 1}

// agent_b acknowledges
message_ack(msg_id="m1")
// => {"status": "acknowledged"}
```

Recipient accepts either `agent_id` or agent `name`.

### RPC (Request-Response)

Synchronous request/response with timeout. The caller sends an `rpc_request`, the responder replies via `parent_msg_id`.

```json
// agent_a sends RPC request
message_send(
  sender_id="a1b2c3d4",
  recipient="agent_b",
  payload="\"{\"action\": \"analyze\", \"target\": \"src/router.py\"}\"",
  msg_type="rpc_request"
)
// => {"msg_id": "m2", "status": "pending"}

// agent_b polls, gets the request
message_poll(agent_id="e5f6g7h8")

// agent_b replies using parent_msg_id
message_reply(
  parent_msg_id="m2",
  sender_id="e5f6g7h8",
  payload="\"{\"result\": \"3 issues found\"}\""
)
// => {"msg_id": "m3", "parent_msg_id": "m2", "status": "pending"}

// agent_a polls for the response
message_poll(agent_id="a1b2c3d4")
```

RPC timeout is configurable via `AGENTSQUAD_RPC_TIMEOUT` (default: 30 seconds).

### Squad Collaboration

Squads are persistent named groups with role-based access.

```json
// agent_a creates a squad (becomes leader)
squad_create(name="backend-team", description="Backend services squad")
// => {"squad_id": "s1", "name": "backend-team"}

// leader invites agent_b as member
squad_join(squad_id="s1", agent_id="e5f6g7h8", role="member", caller_id="a1b2c3d4")

// leader invites agent_c as observer
squad_join(squad_id="s1", agent_id="i9j0k1l2", role="observer", caller_id="a1b2c3d4")

// check squad membership
squad_info(squad_id="s1")
// => {"squad": {...}, "members": [{"agent_id": "a1b2c3d4", "role": "leader"}, ...]}
```

**Permission matrix:**

| Action | leader | member | observer |
|--------|:------:|:------:|:--------:|
| Dissolve squad | Y | N | N |
| Change member roles | Y | N | N |
| Remove member (kick) | Y | N | N |
| Invite agent | Y | N | N |
| Transfer leadership | Y | N | N |
| Send messages | Y | Y | N |
| Subscribe / poll / query | Y | Y | Y |
| Leave squad | Y | Y | Y |

**Transfer leadership** -- leader sets another member's role to `leader`; the current leader is demoted to `member`.

**Dissolve** -- leader calls `squad_dissolve`. All members are removed and the squad is marked inactive.

### Pub/Sub

Topic-based broadcasting with optional squad scoping.

```json
// agent_b subscribes to "alerts" topic
topic_subscribe(agent_id="e5f6g7h8", topic="alerts")
// => {"sub_id": "sub1"}

// agent_c subscribes globally (no squad scope)
topic_subscribe(agent_id="i9j0k1l2", topic="alerts")

// agent_a broadcasts to "alerts"
message_broadcast(sender_id="a1b2c3d4", topic="alerts", payload="\"CPU overload on node-3\"")
// => {"msg_id": "m4", "subscriber_count": 2}
```

**Global subscriptions** -- agents subscribed without a `squad_id` receive broadcasts on that topic from any squad. Squad-scoped subscribers only receive broadcasts within their squad.

### Ad-hoc Team

Temporary cross-squad groups for task forces.

```json
// agent_a forms a team with agent_b and agent_c
team_form(
  initiator_id="a1b2c3d4",
  agent_ids=["e5f6g7h8", "i9j0k1l2"],
  topic="incident-response",
  purpose="Handle production incident"
)
// => {"team_id": "t1", "topic": "incident-response"}

// team members communicate via the team topic
message_broadcast(
  sender_id="e5f6g7h8",
  topic="team:t1",
  payload="\"Root cause identified\""
)

// dismiss when done
team_dismiss(team_id="t1", caller_id="a1b2c3d4")
```

Team messaging uses the reserved `team:<team_id>` topic pattern.

### Agent Pause and Resume

Pause an agent to buffer incoming messages without delivering them.

```json
// pause agent_b
agent_pause(agent_id="e5f6g7h8")
// => {"status": "paused"}

// messages sent to agent_b are buffered...

// resume agent_b
agent_resume(agent_id="e5f6g7h8")
// => {"status": "active", "buffered_count": 3}
```

Only agents in `active` status can be paused. Only agents in `paused` status can be resumed. `buffered_count` reports how many messages were held.

### Heartbeat

Agents signal liveness to the broker. The broker runs a background monitor that marks agents as `disconnected` after the timeout elapses.

```json
heartbeat(agent_id="a1b2c3d4")
// => {"agent_id": "a1b2c3d4", "status": "active", "last_heartbeat": "2025-06-15T10:30:00Z"}
```

- Default interval: 30 seconds (`AGENTSQUAD_HEARTBEAT_INTERVAL`)
- Default timeout: 90 seconds (`AGENTSQUAD_HEARTBEAT_TIMEOUT`)
- A disconnected agent sending a heartbeat is **auto-restored** to `active` status

## Running Tests

```bash
# All 152 tests
uv run pytest

# Smoke test -- 22 checks covering core broker lifecycle
uv run python tests/smoke_test.py

# System test -- 58 checks covering end-to-end flows
uv run python tests/system_test.py
```

Test structure:

```
tests/
  conftest.py                  # Shared fixtures
  test_common/                 # Types and config tests
  test_persistence/            # Store layer tests
  test_broker/                 # Registry, manager, router, heartbeat, core
  test_mcp_server/             # MCP tool integration tests
  test_integration/            # P2P, RPC, Pub/Sub, lifecycle flows
  smoke_test.py                # Quick validation
  system_test.py               # Full end-to-end
```

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

## Troubleshooting

**Broker exits immediately on stdio**

Ensure `PYTHONUNBUFFERED=1` is set in the MCP server env config. Without it, the parent process may not detect the broker's stdout.

**Cannot connect to broker in HTTP mode**

Verify the broker is running and the port matches: `curl http://localhost:8000/mcp`. Check `AGENTSQUAD_HTTP_PORT` and that no other process occupies the port.

**Observer cannot send messages**

Observers have read-only access -- they can subscribe, poll, and query but cannot send messages or broadcast. Assign `member` or `leader` role instead.

**Deregister fails with foreign key error**

The agent likely has active subscriptions, squad memberships, or pending messages. Call `deregister_agent` handles cleanup automatically -- ensure the agent ID exists and is currently registered.

**Messages not delivered after resume**

Paused agents buffer messages. After `agent_resume`, call `message_poll` to retrieve buffered messages. The `buffered_count` in the resume response confirms how many are waiting.
