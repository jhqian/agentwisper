<!-- Copyright 2026 agentsquad contributors, Licensed under the Apache License, Version 2.0 -->

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
# 182 tests collected
```

## Using Tools in MCP Clients

The broker exposes 28 MCP tools via streamable-http transport. In AI-powered clients like Claude Code, you invoke them through **natural language** -- the client translates your request into the appropriate tool call. In programmatic clients, you call tools directly by name.

### Claude Code (with Plugin)

Install the agentsquad plugin to get MCP connection + slash commands:

```bash
claude plugin marketplace add /path/to/agentsquad-plugin
claude plugin install agentsquad
```

Then start the broker in a separate terminal:

```bash
cd agentsquad
uv run agentsquad-broker start --port 8000
```

Now in Claude Code, type:

```
> Register me as an agent named "backend-dev" with code-review capability
```

Claude Code calls `agent_register(name="backend-dev", capabilities=["code-review"])` and returns:

```json
{"agent_id": "agent_d440f761321d4ed0a332", "status": "active"}
```

Available slash commands (provided by the plugin):

| Command | Description |
|---------|-------------|
| `/agentsquad:register <name>` | Register as an agent |
| `/agentsquad:send <recipient> <msg>` | Send P2P message |
| `/agentsquad:sendwait <recipient> <msg> [timeout]` | Send and wait for reply (default 1h) |
| `/agentsquad:poll [all]` | Poll unread messages (or include read with "all") |
| `/agentsquad:wait [timeout]` | Block until messages arrive |
| `/agentsquad:squad <name>` | Create a squad |
| `/agentsquad:invite <agent> [role]` | Invite agent to squad |
| `/agentsquad:broadcast <topic> <msg>` | Broadcast to topic |
| `/agentsquad:subscribe <topic>` | Subscribe to topic |
| `/agentsquad:status [agents]` | Check broker status |

### Claude Code (Manual MCP Config)

If you prefer not to use the plugin, add the MCP server manually:

```bash
claude mcp add --transport http agentsquad-broker http://localhost:8000/mcp
```

Or create `.mcp.json` in your project root:

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

### Programmatic Clients (Python)

Use the MCP SDK directly:

```python
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("agent_register", {
            "name": "my-agent",
            "capabilities": ["code"]
        })
        print(result.content[0].text)
```

## Multi-Agent Setup

Multiple agents connect to a single broker over HTTP.

**1. Start the broker**:

```bash
uv run agentsquad-broker start --port 8000
```

The broker binds to `http://localhost:8000/mcp`.

**2. Configure clients**:

Claude Code (from each agent's project directory):

```bash
claude mcp add --transport http agentsquad-broker http://localhost:8000/mcp
```

OpenCode:

```json
{
  "mcp": {
    "agentsquad-broker": {
      "type": "remote",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Codex:

```bash
codex mcp add agentsquad-broker --transport streamable_http --url "http://localhost:8000/mcp"
```

**3. Register agents** from each client:

```
# Client A: Register me as "agent_a" with code-review capability
# Client B: Register me as "agent_b" with testing capability
# Client C: Register me as "agent_c" with docs capability
```

## Hands-On Demo

Try the complete multi-agent workflow with two Claude Code instances:

```bash
# Terminal 1: Start the broker
cd agentsquad
./samples/start_broker.sh

# Terminal 2: Start Agent A (with plugin installed)
claude

# Terminal 3: Start Agent B (with plugin installed)
claude
```

See `samples/README.md` for the full walkthrough covering P2P messaging, squad collaboration, and pub/sub broadcasting.

## Common Workflows

Below, each workflow shows the **tool signature** (for programmatic use) and a **natural language example** (for Claude Code).

### P2P Messaging

Send a direct message from one agent to another.

**Tool call:**

```
message_send(sender_id="a1b2c3d4", recipient="agent_b", payload="Please review PR #42", msg_type="p2p")
// => {"msg_id": "m1", "status": "sent"}

message_poll(agent_id="e5f6g7h8")
// => {"messages": [{"msg_id": "m1", "sender_id": "a1b2c3d4", "payload": "Please review PR #42"}], "count": 1}
// Messages are automatically acknowledged on delivery
```

**In Claude Code:**

```
> Send a message to agent "tester" saying "Please review PR #42"
```

```
> Check my unread messages
```

Recipient accepts either `agent_id` or agent `name`.

### RPC (Request-Response)

Synchronous request/response with timeout. The caller sends an `rpc_request`, the responder replies via `parent_msg_id`.

**Tool call:**

```
message_send(sender_id="a1b2c3d4", recipient="agent_b", payload='{"action": "analyze"}', msg_type="rpc_request")
// => {"msg_id": "m2", "status": "sent"}

message_poll(agent_id="e5f6g7h8")
// agent_b polls, gets the request

message_send(sender_id="e5f6g7h8", recipient="a1b2c3d4", payload='{"result": "3 issues found"}', msg_type="p2p")
// => {"msg_id": "m3", "status": "sent"}

message_poll(agent_id="a1b2c3d4")
// agent_a polls for the response
```

**In Claude Code:**

```
> Send an RPC request to "tester" asking to analyze src/router.py, wait for the response
```

```
> Send the analysis results back to "reviewer"
```

### Squad Collaboration

Squads are persistent named groups with role-based access.

**Tool call:**

```
squad_create(name="backend-team", caller_id="a1b2c3d4")
// => {"squad_id": "squad_xxx", "role": "leader"}

squad_join(squad_id="s1", agent_id="e5f6g7h8", role="member", caller_id="a1b2c3d4")
squad_join(squad_id="s1", agent_id="i9j0k1l2", role="observer", caller_id="a1b2c3d4")

squad_info(squad_id="s1")
// => {"squad": {...}, "members": [{"agent_id": "a1b2c3d4", "role": "leader"}, ...]}
```

**In Claude Code:**

```
> Create a squad named "backend-team"
```

```
> Invite agent "tester" to join my squad as a member
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

**Tool call:**

```
topic_subscribe(agent_id="e5f6g7h8", topic="alerts")
// => {"sub_id": "sub1"}

topic_subscribe(agent_id="i9j0k1l2", topic="alerts")

message_broadcast(sender_id="a1b2c3d4", topic="alerts", payload="CPU overload on node-3")
// => {"msg_id": "m4", "sent_to": 2}
```

**In Claude Code:**

```
> Subscribe to the "alerts" topic
```

```
> Broadcast "CPU overload on node-3" to the "alerts" topic
```

**Global subscriptions** -- agents subscribed without a `squad_id` receive broadcasts on that topic from any squad. Squad-scoped subscribers only receive broadcasts within their squad.

### Ad-hoc Team

Temporary cross-squad groups for task forces.

**Tool call:**

```
team_form(agent_ids=["a1b2c3d4", "e5f6g7h8", "i9j0k1l2"], topic="incident-response")
// => {"team_id": "team_xxx"}

message_broadcast(sender_id="e5f6g7h8", topic="team:t1", payload="Root cause identified")

team_dismiss(team_id="t1", caller_id="a1b2c3d4")
```

**In Claude Code:**

```
> Form a team with "tester" and "doc-writer" for incident response
```

```
> Broadcast "Root cause identified" to the team
```

Team messaging uses the reserved `team:<team_id>` topic pattern.

### Agent Pause and Resume

Pause an agent to buffer incoming messages without delivering them.

**Tool call:**

```
agent_pause(agent_id="e5f6g7h8")
// => {"status": "paused"}

agent_resume(agent_id="e5f6g7h8")
// => {"status": "active", "buffered_count": 3}
```

**In Claude Code:**

```
> Pause agent "tester"
```

```
> Resume agent "tester"
```

Only agents in `active` status can be paused. Only agents in `paused` status can be resumed. `buffered_count` reports how many messages were held.

### Heartbeat

Agents signal liveness to the broker. The broker runs a background monitor that marks agents as `disconnected` after the timeout elapses.

**Tool call:**

```
heartbeat(agent_id="a1b2c3d4")
// => {"status": "active", "last_heartbeat": "2026-05-11T04:52:42Z"}
```

**In Claude Code:**

```
> Send a heartbeat to keep my agent alive
```

- Default interval: 30 seconds (`AGENTSQUAD_HEARTBEAT_INTERVAL`)
- Default timeout: 90 seconds (`AGENTSQUAD_HEARTBEAT_TIMEOUT`)
- A disconnected agent sending a heartbeat is **auto-restored** to `active` status

### Message Notification

When a message is delivered (P2P, RPC reply, or Pub/Sub broadcast), the broker triggers the recipient's `anyio.Event` if they are actively waiting. Agents detect new messages via two mechanisms:

1. **`message_wait`** (recommended) -- blocks until a message arrives. Zero latency for idle agents.
2. **`message_poll`** -- queries the database for pending messages. Returns all unread messages.

Messages are stored in SQLite until delivered via `message_poll` or `message_wait`.

**Tool count:** The broker exposes **26 MCP tools**.

### message_wait

Block until messages arrive, with optional timeout. Returns immediately if pending messages exist.

**Tool call:**

```
message_wait(agent_id="e5f6g7h8", timeout=30)
// => {"messages": [...], "count": 1, "waited": true}
```

**In Claude Code:**

```
> Wait up to 30 seconds for new messages
```

- `timeout=0` returns immediately (non-blocking poll)
- Default timeout: 30 seconds
- Returns `waited: true` if it actually blocked, `false` if messages were already pending

### agent_wake

Wake a paused or disconnected agent and optionally inject a message. Inspired by Claude Code's instance activation pattern.

**Tool call:**

```
agent_wake(agent_id="e5f6g7h8", message="Please review the latest changes")
// => {"status": "active", "message_queued": true}
```

**In Claude Code:**

```
> Wake agent "tester" and tell it to run the test suite
```

- If the agent is `paused` or `disconnected`, it is restored to `active`
- The optional `message` parameter injects a system notification that the agent receives on its next poll
- This enables agent-to-agent activation: one agent can start another

## Running Tests

```bash
# All 182 unit tests
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
| `AGENTSQUAD_HTTP_PORT` | `8000` | Port for streamable-http transport |

## Troubleshooting

**Cannot connect to broker**

Verify the broker is running and the port matches: `curl http://localhost:8000/mcp`. Check `AGENTSQUAD_HTTP_PORT` and that no other process occupies the port.

**MCP server not appearing in Claude Code**

Claude Code reads MCP server configuration from `.mcp.json` in the project root. Use `claude mcp add` or install the agentsquad plugin. Run `/mcp` to verify the server is listed.

**Observer cannot send messages**

Observers have read-only access -- they can subscribe, poll, and query but cannot send messages or broadcast. Assign `member` or `leader` role instead.

**Deregister fails with foreign key error**

The agent likely has active subscriptions, squad memberships, or pending messages. Call `deregister_agent` handles cleanup automatically -- ensure the agent ID exists and is currently registered.

**Messages not delivered after resume**

Paused agents buffer messages. After `agent_resume`, call `message_poll` to retrieve buffered messages. The `buffered_count` in the resume response confirms how many are waiting.
