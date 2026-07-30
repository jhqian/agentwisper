<!-- Copyright 2026 agentwisper contributors, Licensed under the Apache License, Version 2.0 -->

# Multi-Agent Demo

A hands-on demo showing two Claude Code instances communicating through the agentwisper broker via MCP tools.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.12+ | Required |
| [uv](https://docs.astral.sh/uv/) | Package manager |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | CLI with MCP support |
| agentwisper plugin | Install via `claude plugin add` |

## Setup

Install the broker (from the `agentwisper/` directory):

```bash
cd agentwisper
uv sync
```

Install the agentwisper plugin in Claude Code:

```bash
claude plugin add --dev /path/to/agentwisper-plugin
```

## Running the Demo

You need **3 terminal windows**.

### Terminal 1: Start the Broker

```bash
cd agentwisper
./samples/start_broker.sh
```

Wait for the "Broker URL: http://localhost:8000/mcp" message.

### Terminal 2: Start Agent A (code-reviewer)

```bash
claude
```

### Terminal 3: Start Agent B (tester)

```bash
claude
```

## Demo Scenario

Each step below shows the slash command and the equivalent natural language.

### Phase 1: Register Agents

**In Agent A's terminal**, register with the slash command:

```
/agentwisper:register code-reviewer
```

Or natural language:

```
Use the agentwisper-broker MCP server to register an agent named "code-reviewer"
with capabilities ["code-review", "refactoring"].
```

This calls `agent_register(name="code-reviewer", capabilities=["code-review", "refactoring"])`.

Note the `agent_id` from the response -- you'll need it in subsequent steps.

**In Agent B's terminal**, register the tester:

```
/agentwisper:register tester
```

Or natural language:

```
Use the agentwisper-broker MCP server to register an agent named "tester"
with capabilities ["testing", "debugging"].
```

Note Agent B's `agent_id` as well.

### Phase 2: P2P Messaging

**Agent A** sends a message to Agent B:

```
/agentwisper:send tester Please run the integration tests for PR #42
```

Or send and wait for reply in one command:

```
/agentwisper:sendwait tester Please run the integration tests for PR #42
```

Or natural language:

```
Use agentwisper-broker to send a P2P message from my agent to "tester"
with payload "Please run the integration tests for PR #42".
```

This calls `message_send(sender_id="<agent_a_id>", recipient="tester", payload="...", msg_type="p2p")`.

The broker resolves "tester" to Agent B's ID automatically.

If using `/agentwisper:sendwait`, the command also calls `message_wait` after sending, blocking until tester replies (default timeout: 1 hour).

**Agent B** receives the message using one of two methods:

**Method 1: Blocking wait** (zero latency, recommended for idle agents):

```
/agentwisper:wait 60
```

Or natural language:

```
Use agentwisper-broker to wait up to 60 seconds for new messages addressed to me.
```

This calls `message_wait(agent_id="<agent_b_id>", timeout=60)`. The call blocks until a message arrives or the timeout expires.

**Method 2: Direct poll** (lightweight, for agents between tasks):

```
/agentwisper:poll
```

This queries the database for pending messages and returns them immediately.

**Agent B** replies:

```
/agentwisper:send code-reviewer Tests passed: 182/182, 0 failures
```

This calls `message_send(sender_id="<agent_b_id>", recipient="code-reviewer", payload="...", msg_type="p2p")`.

**Agent A** checks for the reply:

```
/agentwisper:poll
```

### Phase 3: Squad Collaboration

**Agent A** creates a squad and invites Agent B:

```
/agentwisper:squad pr-review-team
```

Then invite:

```
/agentwisper:invite tester member
```

This calls:
1. `squad_create(name="pr-review-team", caller_id="<agent_a_id>")`
2. `squad_join(squad_id="<squad_id>", agent_id="<agent_b_id>", role="member", caller_id="<agent_a_id>")`

**Agent B** subscribes to a topic:

```
/agentwisper:subscribe progress
```

This calls `topic_subscribe(agent_id="<agent_b_id>", topic="progress")`.

**Agent A** broadcasts a progress update:

```
/agentwisper:broadcast progress PR #42 review complete, all tests passing. Ready to merge.
```

This calls `message_broadcast(sender_id="<agent_a_id>", topic="progress", payload="...")`.

**Agent B** receives the broadcast:

```
/agentwisper:poll
```

### Phase 4: Cleanup

**Agent A** (leader) can dissolve the squad:

```
Dissolve the squad.
```

Both agents deregister:

```
Deregister my agent from the agentwisper-broker.
```

This calls `agent_deregister(agent_id="<agent_id>")`.

## What You Learned

- **P2P Messaging**: Direct agent-to-agent communication with name-based addressing
- **RPC Pattern**: Request/response with `message_send` in both directions
- **Squad Management**: Leader/member roles, invite, join, dissolve
- **Pub/Sub Broadcasting**: Topic subscriptions and message broadcasting
- **Name Resolution**: The broker resolves agent names ("tester") to IDs automatically
- **Blocking Wait**: `message_wait` blocks until messages arrive (zero latency for idle agents)

## Next Steps

- Try the **RPC pattern**: Send a message with `msg_type="rpc_request"` and respond via `message_send` back to the caller
- Experiment with **roles**: Make Agent B an `observer` -- it can subscribe and poll but cannot send messages
- Add a **third agent**: Start another Claude Code instance with the plugin installed
- Test **blocking wait**: Use `/agentwisper:wait 30` on Agent B, then send a message from Agent A -- the wait should return immediately

## Cleanup

Remove the database:

```bash
rm -f /tmp/agentwisper_demo.db
```

## Troubleshooting

**"Cannot connect to broker"** -- Ensure the broker is running in Terminal 1 and port 8000 is free.

**"Agent not found"** -- Register the agent first before sending messages to it.

**MCP tools not appearing** -- Run `/mcp` to verify the agentwisper-broker server is listed. If not, check that the plugin is installed correctly.
