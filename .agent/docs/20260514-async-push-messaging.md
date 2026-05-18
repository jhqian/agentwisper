# Async Push Messaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time MCP notification push so agents receive messages instantly without polling, plus a `message_wait` blocking tool and `agent_wake` instance activation.

**Architecture:** When a message is persisted, the broker looks up the recipient's MCP session in a SessionRegistry and pushes a `LoggingMessageNotification` via SSE. If no active session exists, the message stays in SQLite for later poll. A `message_wait` tool provides blocking semantics (with timeout) for agents that need synchronous receive. An `agent_wake` tool lets one agent resume a paused agent and inject a prompt.

**Tech Stack:** Python 3.12+, MCP SDK `mcp[cli]>=1.0`, FastMCP `LoggingMessageNotification`, `anyio` for async primitives, SQLite (existing)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/broker/session_registry.py` | Create | Track agent_id -> set of notification callbacks |
| `src/broker/core.py` | Modify | Wire SessionRegistry, add notification dispatch after message ops |
| `src/broker/router.py` | Modify | Accept optional `on_message_delivered` callback, invoke after persist |
| `src/mcp_server/server.py` | Modify | Register/unregister sessions on agent_register/heartbeat/deregister; add `message_wait` and `agent_wake` tools |
| `src/common/types.py` | No change | Existing types are sufficient |
| `tests/test_broker/test_session_registry.py` | Create | Unit tests for SessionRegistry |
| `tests/test_broker/test_push_integration.py` | Create | Integration tests for push notification flow |

---

### Task 1: Create SessionRegistry

**Files:**
- Create: `src/broker/session_registry.py`
- Test: `tests/test_broker/test_session_registry.py`

SessionRegistry tracks agent_id -> set of async callback functions. When a message arrives, the broker calls `notify_agent(agent_id, notification_data)` which invokes all registered callbacks for that agent. This decouples the notification mechanism from MCP specifics — the MCP server layer registers callbacks that send MCP notifications.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_broker/test_session_registry.py
# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Tests for SessionRegistry async push notification dispatch."""

import pytest
from broker.session_registry import SessionRegistry


@pytest.fixture
def registry():
    return SessionRegistry()


async def test_register_and_notify(registry):
    received = []
    async def callback(data):
        received.append(data)

    registry.register("agent_001", callback)
    await registry.notify_agent("agent_001", {"msg_id": "msg_123", "sender": "agent_002"})

    assert len(received) == 1
    assert received[0]["msg_id"] == "msg_123"


async def test_notify_no_registered_sessions_silently_passes(registry):
    # Should not raise — agent may be offline
    await registry.notify_agent("agent_unknown", {"msg_id": "msg_x"})


async def test_unregister(registry):
    received = []
    async def callback(data):
        received.append(data)

    registry.register("agent_001", callback)
    registry.unregister("agent_001", callback)
    await registry.notify_agent("agent_001", {"msg_id": "msg_123"})

    assert len(received) == 0


async def test_multiple_callbacks_for_same_agent(registry):
    received_a = []
    received_b = []
    async def cb_a(data):
        received_a.append(data)
    async def cb_b(data):
        received_b.append(data)

    registry.register("agent_001", cb_a)
    registry.register("agent_001", cb_b)
    await registry.notify_agent("agent_001", {"msg_id": "msg_1"})

    assert len(received_a) == 1
    assert len(received_b) == 1


async def test_unregister_one_of_multiple_callbacks(registry):
    received_a = []
    received_b = []
    async def cb_a(data):
        received_a.append(data)
    async def cb_b(data):
        received_b.append(data)

    registry.register("agent_001", cb_a)
    registry.register("agent_001", cb_b)
    registry.unregister("agent_001", cb_a)
    await registry.notify_agent("agent_001", {"msg_id": "msg_1"})

    assert len(received_a) == 0
    assert len(received_b) == 1


async def test_notify_different_agents_isolated(registry):
    received_a = []
    received_b = []
    async def cb_a(data):
        received_a.append(data)
    async def cb_b(data):
        received_b.append(data)

    registry.register("agent_001", cb_a)
    registry.register("agent_002", cb_b)
    await registry.notify_agent("agent_001", {"msg_id": "msg_1"})

    assert len(received_a) == 1
    assert len(received_b) == 0


async def test_unregister_all_clears_agent_entry(registry):
    received = []
    async def cb(data):
        received.append(data)

    registry.register("agent_001", cb)
    registry.unregister("agent_001", cb)
    assert registry.has_sessions("agent_001") is False


async def test_unregister_nonexistent_does_not_raise(registry):
    async def dummy(data):
        pass
    registry.unregister("agent_999", dummy)


async def test_notify_broadcast_to_all_sessions(registry):
    received = []
    async def cb1(data):
        received.append(("cb1", data))
    async def cb2(data):
        received.append(("cb2", data))

    registry.register("agent_001", cb1)
    registry.register("agent_001", cb2)
    await registry.notify_agent("agent_001", {"msg_id": "msg_broadcast"})

    assert len(received) == 2
    sources = {r[0] for r in received}
    assert sources == {"cb1", "cb2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/test_broker/test_session_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'broker.session_registry'`

- [ ] **Step 3: Write SessionRegistry implementation**

```python
# src/broker/session_registry.py
# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Session registry for tracking agent notification callbacks."""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Type alias: async callback that accepts a notification data dict
NotificationCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class SessionRegistry:
    """Tracks agent_id -> set of notification callbacks.

    When a message is delivered, the broker calls notify_agent() which
    invokes all registered callbacks for that agent. The MCP server layer
    registers callbacks that send LoggingMessageNotification via SSE.

    This decoupling keeps the broker layer independent of MCP specifics.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, set[NotificationCallback]] = {}

    def register(self, agent_id: str, callback: NotificationCallback) -> None:
        """Register a notification callback for an agent."""
        if agent_id not in self._sessions:
            self._sessions[agent_id] = set()
        self._sessions[agent_id].add(callback)

    def unregister(self, agent_id: str, callback: NotificationCallback) -> None:
        """Remove a specific callback for an agent."""
        callbacks = self._sessions.get(agent_id)
        if callbacks is None:
            return
        callbacks.discard(callback)
        if not callbacks:
            del self._sessions[agent_id]

    def has_sessions(self, agent_id: str) -> bool:
        """Check if an agent has any registered notification callbacks."""
        return bool(self._sessions.get(agent_id))

    async def notify_agent(self, agent_id: str, data: dict[str, Any]) -> None:
        """Push notification data to all callbacks registered for an agent.

        Silently skips if agent has no registered callbacks (offline or
        never registered). Logs but does not raise on callback errors.
        """
        callbacks = self._sessions.get(agent_id)
        if not callbacks:
            return
        for cb in list(callbacks):
            try:
                await cb(data)
            except Exception:
                logger.exception("Notification callback failed for agent %s", agent_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/test_broker/test_session_registry.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/broker/session_registry.py tests/test_broker/test_session_registry.py
git commit -m "feat: add SessionRegistry for agent notification callbacks"
```

---

### Task 2: Wire SessionRegistry into Broker core

**Files:**
- Modify: `src/broker/core.py`

Add SessionRegistry to the Broker. When `send_message`, `broadcast_message`, or `reply_message` completes, call `_notify_recipients()` to push notifications to relevant agents.

- [ ] **Step 1: Write the failing test**

Add tests to `tests/test_broker/test_broker_core.py` that verify the broker dispatches notifications via SessionRegistry after message operations.

```python
# Append to tests/test_broker/test_broker_core.py

async def test_broker_notifies_recipient_on_send(broker):
    received = []
    async def callback(data):
        received.append(data)

    r1 = await broker.register_agent("sender", [])
    r2 = await broker.register_agent("receiver", [])
    broker.session_registry.register(r2["agent_id"], callback)

    await broker.send_message(r1["agent_id"], r2["agent_id"], '{"hello": true}', "p2p")

    assert len(received) == 1
    assert received[0]["msg_id"].startswith("msg_")
    assert received[0]["sender_id"] == r1["agent_id"]
    assert received[0]["msg_type"] == "p2p"


async def test_broker_notifies_subscribers_on_broadcast(broker):
    received_a = []
    received_b = []
    async def cb_a(data):
        received_a.append(data)
    async def cb_b(data):
        received_b.append(data)

    r1 = await broker.register_agent("publisher", [])
    r2 = await broker.register_agent("sub_a", [])
    r3 = await broker.register_agent("sub_b", [])
    await broker.subscribe_topic(r2["agent_id"], "alerts")
    await broker.subscribe_topic(r3["agent_id"], "alerts")

    broker.session_registry.register(r2["agent_id"], cb_a)
    broker.session_registry.register(r3["agent_id"], cb_b)

    await broker.broadcast_message(r1["agent_id"], "alerts", '{"level": "critical"}')

    assert len(received_a) == 1
    assert len(received_b) == 1


async def test_broker_notifies_on_reply(broker):
    received = []
    async def callback(data):
        received.append(data)

    r1 = await broker.register_agent("requester", [])
    r2 = await broker.register_agent("responder", [])

    broker.session_registry.register(r1["agent_id"], callback)

    msg = await broker.send_message(r1["agent_id"], r2["agent_id"], '{"task": "review"}', "rpc_request")
    await broker.reply_message(msg["msg_id"], r2["agent_id"], '{"result": "ok"}')

    assert len(received) == 1
    assert received[0]["msg_type"] == "rpc_response"
    assert received[0]["parent_msg_id"] == msg["msg_id"]


async def test_broker_exposes_session_registry(broker):
    assert broker.session_registry is not None
    assert hasattr(broker.session_registry, "register")
    assert hasattr(broker.session_registry, "notify_agent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/test_broker/test_broker_core.py::test_broker_exposes_session_registry -v`
Expected: FAIL — `AssertionError` (broker has no `session_registry` attribute)

- [ ] **Step 3: Modify Broker core to wire SessionRegistry and notification dispatch**

Edit `src/broker/core.py`:

1. Import `SessionRegistry`
2. Add `self.session_registry = SessionRegistry()` in `__init__`
3. Add `_notify_recipients()` helper that pushes notification data
4. Call `_notify_recipients()` after `send_message`, `broadcast_message`, `reply_message`

```python
# src/broker/core.py — full replacement

# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Broker core orchestrator wiring all components together."""

from __future__ import annotations

import logging
from typing import Any

from common.config import BrokerConfig
from common.types import MessageType
from persistence.database import AsyncDatabase
from persistence.subscription_store import SubscriptionStore
from broker.agent_registry import AgentRegistry
from broker.heartbeat import HeartbeatMonitor
from broker.router import MessageRouter
from broker.session_registry import SessionRegistry
from broker.squad_manager import SquadManager
from broker.team_manager import TeamManager

logger = logging.getLogger(__name__)


class Broker:
    """Top-level orchestrator that holds all components and provides a
    unified API for the MCP Server layer.

    Delegates each operation to the appropriate manager while managing
    the shared database connection and heartbeat monitor lifecycle.
    """

    def __init__(self, config: BrokerConfig) -> None:
        self._config = config
        self._db = AsyncDatabase(config.db_path)
        self._registry = AgentRegistry(self._db)
        self._squad_mgr = SquadManager(self._db)
        self._team_mgr = TeamManager(self._db)
        self._router = MessageRouter(self._db)
        self._heartbeat = HeartbeatMonitor(
            self._db, config.heartbeat_interval, config.heartbeat_timeout
        )
        self._sub_store = SubscriptionStore(self._db)
        self.session_registry = SessionRegistry()
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize database and start background services."""
        if self._started:
            return
        await self._db.initialize()
        await self._heartbeat.start()
        self._started = True

    async def stop(self) -> None:
        """Stop background services and close database."""
        if not self._started:
            return
        await self._heartbeat.stop()
        await self._db.close()
        self._started = False

    # ------------------------------------------------------------------
    # Notification dispatch
    # ------------------------------------------------------------------

    async def _notify_recipients(
        self,
        recipient_ids: list[str],
        notification: dict[str, Any],
    ) -> None:
        """Push notification to recipients via SessionRegistry.

        Silently skips agents with no registered sessions. Errors in
        individual callbacks are logged but do not block other recipients.
        """
        for agent_id in recipient_ids:
            try:
                await self.session_registry.notify_agent(agent_id, notification)
            except Exception:
                logger.exception("Failed to notify agent %s", agent_id)

    def _make_notification(
        self,
        msg_id: str,
        sender_id: str,
        msg_type: str,
        payload: str,
        *,
        topic: str | None = None,
        parent_msg_id: str | None = None,
        squad_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a notification payload for push delivery."""
        notif: dict[str, Any] = {
            "event": "message_received",
            "msg_id": msg_id,
            "sender_id": sender_id,
            "msg_type": msg_type,
            "payload_preview": payload[:200] if payload else "",
        }
        if topic is not None:
            notif["topic"] = topic
        if parent_msg_id is not None:
            notif["parent_msg_id"] = parent_msg_id
        if squad_id is not None:
            notif["squad_id"] = squad_id
        return notif

    # ------------------------------------------------------------------
    # Agent operations  (delegates to AgentRegistry)
    # ------------------------------------------------------------------

    async def register_agent(
        self,
        name: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        agent_id = await self._registry.register(name, capabilities, metadata)
        return {"agent_id": agent_id, "status": "active"}

    async def deregister_agent(self, agent_id: str) -> dict:
        self.session_registry.unregister_all(agent_id)
        await self._registry.deregister(agent_id)
        return {"status": "deregistered"}

    async def pause_agent(self, agent_id: str) -> dict:
        await self._registry.pause(agent_id)
        return {"status": "paused"}

    async def resume_agent(self, agent_id: str) -> dict:
        return await self._registry.resume(agent_id)

    async def agent_heartbeat(self, agent_id: str) -> dict:
        await self._registry.heartbeat(agent_id)
        info = await self._registry.get_info(agent_id)
        return {"last_heartbeat": info["last_heartbeat"], "status": info["status"]}

    async def get_agent_info(self, agent_id: str) -> dict | None:
        return await self._registry.get_info(agent_id)

    async def list_agents(self, squad_id: str | None = None) -> dict:
        agents = await self._registry.list_agents(squad_id)
        return {"agents": agents}

    # ------------------------------------------------------------------
    # Squad operations  (delegates to SquadManager)
    # ------------------------------------------------------------------

    async def create_squad(
        self,
        name: str,
        caller_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        squad_id = await self._squad_mgr.create(name, caller_id, metadata)
        return {"squad_id": squad_id, "role": "leader"}

    async def dissolve_squad(self, squad_id: str, caller_id: str) -> dict:
        await self._squad_mgr.dissolve(squad_id, caller_id)
        return {"status": "dissolved"}

    async def join_squad(
        self, squad_id: str, agent_id: str, role: str, caller_id: str
    ) -> dict:
        await self._squad_mgr.join(squad_id, agent_id, role, caller_id)
        return {"status": "joined", "squad_id": squad_id, "role": role}

    async def leave_squad(self, agent_id: str) -> dict:
        await self._squad_mgr.leave(agent_id)
        return {"status": "left"}

    async def kick_from_squad(
        self, squad_id: str, agent_id: str, caller_id: str
    ) -> dict:
        await self._squad_mgr.kick(squad_id, agent_id, caller_id)
        return {"status": "kicked"}

    async def set_squad_role(
        self, squad_id: str, agent_id: str, role: str, caller_id: str
    ) -> dict:
        await self._squad_mgr.set_role(squad_id, agent_id, role, caller_id)
        return {"status": "role_updated", "new_role": role}

    async def get_squad_info(self, squad_id: str) -> dict:
        return await self._squad_mgr.get_info(squad_id)

    async def list_squads(self) -> dict:
        squads = await self._squad_mgr.list_squads()
        return {"squads": squads}

    # ------------------------------------------------------------------
    # Team operations  (delegates to TeamManager)
    # ------------------------------------------------------------------

    async def form_team(
        self,
        initiator_id: str,
        agent_ids: list[str],
        topic: str | None = None,
        ttl_seconds: int | None = None,
    ) -> dict:
        team_id = await self._team_mgr.form(initiator_id, agent_ids, topic, ttl_seconds)
        return {"team_id": team_id}

    async def dismiss_team(self, team_id: str, caller_id: str) -> dict:
        await self._team_mgr.dismiss(team_id, caller_id)
        return {"status": "dismissed"}

    async def get_team_info(self, team_id: str) -> dict:
        return await self._team_mgr.get_info(team_id)

    async def list_teams(self, agent_id: str | None = None) -> dict:
        teams = await self._team_mgr.list_teams(agent_id)
        return {"teams": teams}

    # ------------------------------------------------------------------
    # Message operations  (delegates to MessageRouter)
    # ------------------------------------------------------------------

    async def send_message(
        self,
        sender_id: str,
        recipient: str,
        payload: str,
        msg_type: str = "p2p",
        squad_id: str | None = None,
    ) -> dict:
        result = await self._router.send_message(
            sender_id, recipient, payload, MessageType(msg_type), squad_id
        )
        # Push notification to recipient
        recipient_id = result.get("recipient_id", recipient)
        notif = self._make_notification(
            msg_id=result["msg_id"],
            sender_id=sender_id,
            msg_type=msg_type,
            payload=payload,
            squad_id=squad_id,
        )
        await self._notify_recipients([recipient_id], notif)
        return result

    async def broadcast_message(
        self,
        sender_id: str,
        topic: str,
        payload: str,
        squad_id: str | None = None,
    ) -> dict:
        result = await self._router.broadcast_message(
            sender_id, topic, payload, squad_id
        )
        # Push notification to all subscribers
        subscriber_ids = result.get("subscriber_ids", [])
        if subscriber_ids:
            notif = self._make_notification(
                msg_id=result["msg_id"],
                sender_id=sender_id,
                msg_type="pubsub",
                payload=payload,
                topic=topic,
                squad_id=squad_id,
            )
            await self._notify_recipients(subscriber_ids, notif)
        return result

    async def reply_message(
        self, parent_msg_id: str, sender_id: str, payload: str
    ) -> dict:
        result = await self._router.reply_message(parent_msg_id, sender_id, payload)
        # Push notification to original requester
        original_sender = result.get("recipient_id")
        if original_sender:
            notif = self._make_notification(
                msg_id=result["msg_id"],
                sender_id=sender_id,
                msg_type="rpc_response",
                payload=payload,
                parent_msg_id=parent_msg_id,
            )
            await self._notify_recipients([original_sender], notif)
        return result

    async def poll_messages(
        self, agent_id: str, limit: int = 50, unread_only: bool = True
    ) -> dict:
        messages = await self._router.poll_messages(agent_id, limit, unread_only)
        return {"messages": messages}

    async def acknowledge_message(self, msg_id: str) -> dict:
        await self._router.acknowledge_message(msg_id)
        return {"status": "acknowledged"}

    async def acknowledge_delivery(self, delivery_id: str) -> dict:
        await self._router.acknowledge_delivery(delivery_id)
        return {"status": "acknowledged"}

    # ------------------------------------------------------------------
    # Subscription operations  (delegates to SubscriptionStore)
    # ------------------------------------------------------------------

    async def subscribe_topic(
        self, agent_id: str, topic: str, squad_id: str | None = None
    ) -> dict:
        sub_id = await self._sub_store.create(agent_id, topic, squad_id)
        return {"sub_id": sub_id}

    async def unsubscribe_topic(self, sub_id: str) -> dict:
        await self._sub_store.delete(sub_id)
        return {"status": "unsubscribed"}

    # ------------------------------------------------------------------
    # System operations
    # ------------------------------------------------------------------

    async def broker_status(self) -> dict:
        agents = await self._registry.list_agents()
        return {
            "status": "healthy" if self._started else "stopped",
            "active_agents": len(agents),
        }
```

- [ ] **Step 4: Add `unregister_all` to SessionRegistry and fix router return values**

SessionRegistry needs `unregister_all` for deregistration. The router also needs to return `recipient_id` and `subscriber_ids` so the broker knows who to notify.

Add to `src/broker/session_registry.py` after the `unregister` method:

```python
    def unregister_all(self, agent_id: str) -> None:
        """Remove all callbacks for an agent (used on deregister)."""
        self._sessions.pop(agent_id, None)
```

Modify `src/broker/router.py` — `send_message` to return recipient_id:

```python
        return {"msg_id": msg_id, "status": "pending", "recipient_id": recipient_id}
```

Modify `src/broker/router.py` — `broadcast_message` to return subscriber_ids:

```python
        if subscriber_ids:
            await self._message_store.create_delivery_logs(msg_id, subscriber_ids)

        return {
            "msg_id": msg_id,
            "subscriber_count": len(subscriber_ids),
            "subscriber_ids": subscriber_ids,
        }
```

Modify `src/broker/router.py` — `reply_message` to return recipient_id:

```python
        return {"msg_id": msg_id, "status": "pending", "recipient_id": original_sender}
```

- [ ] **Step 5: Run tests to verify**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/test_broker/test_broker_core.py -v`
Expected: All existing tests pass (new return fields are additive) + new notification tests pass

Also run: `uv run pytest tests/ -v`
Expected: All 152+ existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/broker/core.py src/broker/session_registry.py src/broker/router.py tests/test_broker/test_broker_core.py
git commit -m "feat: wire SessionRegistry into broker for push notifications on message delivery"
```

---

### Task 3: Add MCP notification push in server.py

**Files:**
- Modify: `src/mcp_server/server.py`

Register notification callbacks with SessionRegistry when agents call `agent_register` or `heartbeat`. The callback sends a `LoggingMessageNotification` to the calling client's MCP session via `ctx.info()` (which uses `send_log_message` under the hood).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mcp_server.py`:

```python
async def test_agent_register_creates_session_binding():
    """Verify that agent_register creates a notification callback in SessionRegistry."""
    from broker.session_registry import SessionRegistry
    from broker.core import Broker
    from common.config import BrokerConfig

    config = BrokerConfig(db_path=":memory:")
    broker = Broker(config)
    await broker.start()
    assert broker.session_registry is not None

    # Registering an agent via broker core should NOT auto-register a callback
    # (that happens at MCP server level), so check it's empty
    result = await broker.register_agent("test-agent", ["code"])
    assert not broker.session_registry.has_sessions(result["agent_id"])
    await broker.stop()


async def test_manual_session_registration_and_push():
    """Verify that manually registering a callback allows push notifications."""
    from broker.core import Broker
    from common.config import BrokerConfig

    config = BrokerConfig(db_path=":memory:")
    broker = Broker(config)
    await broker.start()

    received = []
    async def test_callback(data):
        received.append(data)

    r1 = await broker.register_agent("sender", [])
    r2 = await broker.register_agent("receiver", [])
    broker.session_registry.register(r2["agent_id"], test_callback)

    await broker.send_message(r1["agent_id"], r2["agent_id"], '{"push": true}', "p2p")

    assert len(received) == 1
    assert received[0]["event"] == "message_received"
    assert received[0]["sender_id"] == r1["agent_id"]
    await broker.stop()
```

- [ ] **Step 2: Run test to verify**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/test_mcp_server.py -v`
Expected: PASS (these test broker-level behavior, already supported by Task 2)

- [ ] **Step 3: Modify server.py to bind sessions on register/heartbeat**

The key insight: in MCP, each tool call gets a `Context` with access to the current session. We create a closure that captures the session and sends a notification when invoked. This closure is registered with SessionRegistry.

Modify `src/mcp_server/server.py` — add a helper function and modify `agent_register` and `heartbeat`:

```python
# Add after _resolve_agent function:

def _make_push_callback(ctx: Context):
    """Create a notification callback that pushes via MCP session."""
    async def push_notification(data: dict) -> None:
        try:
            import json
            await ctx.info(json.dumps(data))
        except Exception:
            pass  # Session may have disconnected
    return push_notification
```

Modify `agent_register` to register the callback:

```python
@mcp.tool()
async def agent_register(
    name: str,
    capabilities: list[str],
    metadata: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> dict:
    """Register a new agent and bind push notification to caller's session. Returns agent_id and status."""
    broker = _get_broker(ctx)
    result = await broker.register_agent(name, capabilities, metadata)
    if ctx is not None:
        callback = _make_push_callback(ctx)
        broker.session_registry.register(result["agent_id"], callback)
    return result
```

Modify `heartbeat` to re-register the callback (keeps binding fresh):

```python
@mcp.tool()
async def heartbeat(agent_id: str, ctx: Context | None = None) -> dict:
    """Signal agent is alive and refresh push notification binding. agent_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    result = await broker.agent_heartbeat(agent_id)
    if ctx is not None:
        callback = _make_push_callback(ctx)
        broker.session_registry.register(agent_id, callback)
    return result
```

Modify `agent_deregister` to clean up:

```python
@mcp.tool()
async def agent_deregister(agent_id: str, ctx: Context | None = None) -> dict:
    """Remove an agent and unbind push notifications. Accepts agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    return await broker.deregister_agent(agent_id)
```

- [ ] **Step 4: Run all tests**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/ -v`
Expected: All tests pass — the MCP server changes are additive

- [ ] **Step 5: Commit**

```bash
git add src/mcp_server/server.py tests/test_mcp_server.py
git commit -m "feat: bind MCP push notifications to agent sessions on register and heartbeat"
```

---

### Task 4: Add `message_wait` blocking tool

**Files:**
- Modify: `src/mcp_server/server.py`

A new MCP tool that blocks until a message arrives for the agent, with optional timeout. Uses `anyio.Event` — the SessionRegistry callback sets the event, and `message_wait` awaits it. Falls back to immediate poll first.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_broker/test_broker_core.py`:

```python
async def test_broker_wait_mechanism(broker):
    """Test that message_wait returns immediately when messages are pending."""
    r1 = await broker.register_agent("sender", [])
    r2 = await broker.register_agent("receiver", [])

    # Send a message first
    await broker.send_message(r1["agent_id"], r2["agent_id"], '{"ready": true}', "p2p")

    # Poll should return the message
    result = await broker.poll_messages(r2["agent_id"])
    assert len(result["messages"]) >= 1
```

- [ ] **Step 2: Implement `message_wait` tool in server.py**

The `message_wait` tool at the MCP server level uses a combination of immediate poll + Event-based wait:

```python
@mcp.tool()
async def message_wait(
    agent_id: str,
    timeout: int = 30,
    limit: int = 50,
    ctx: Context | None = None,
) -> dict:
    """Block until messages arrive, with timeout. Returns messages immediately if any pending. agent_id accepts agent_id or name.

    Args:
        agent_id: Agent to wait for. Accepts agent_id or name.
        timeout: Max seconds to wait (default 30, 0 for no wait).
        limit: Max messages to return.
    """
    import anyio
    import json

    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)

    # First, check for existing pending messages
    result = await broker.poll_messages(agent_id, limit, unread_only=True)
    msgs = result.get("messages", [])
    if msgs:
        return {"messages": msgs, "total": len(msgs), "waited": False}

    if timeout <= 0:
        return {"messages": [], "total": 0, "waited": False}

    # No messages yet — set up event-based wait
    message_event = anyio.Event()

    async def on_message(data: dict) -> None:
        message_event.set()

    broker.session_registry.register(agent_id, on_message)
    try:
        with anyio.fail_after(timeout):
            await message_event.wait()
        waited = True
    except TimeoutError:
        waited = False
    finally:
        broker.session_registry.unregister(agent_id, on_message)

    # After wake-up, poll for actual messages
    result = await broker.poll_messages(agent_id, limit, unread_only=True)
    msgs = result.get("messages", [])
    return {"messages": msgs, "total": len(msgs), "waited": waited}
```

- [ ] **Step 3: Run all tests**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/mcp_server/server.py tests/test_broker/test_broker_core.py
git commit -m "feat: add message_wait tool for blocking message receive with timeout"
```

---

### Task 5: Add `agent_wake` tool

**Files:**
- Modify: `src/mcp_server/server.py`
- Modify: `src/broker/core.py`

New tool inspired by Claude Code's `resumeAgentBackground()`. Allows one agent to wake a paused/disconnected agent and optionally inject a message as prompt. This enables agent-to-agent activation.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_broker/test_broker_core.py`:

```python
async def test_broker_wake_agent(broker):
    r = await broker.register_agent("sleepy", [])
    await broker.pause_agent(r["agent_id"])
    info = await broker.get_agent_info(r["agent_id"])
    assert info["status"] == "paused"

    result = await broker.wake_agent(r["agent_id"], message="Wake up!")
    assert result["status"] == "active"
    assert result["message_queued"] is True

    info = await broker.get_agent_info(r["agent_id"])
    assert info["status"] == "active"


async def test_broker_wake_already_active_agent(broker):
    r = await broker.register_agent("active-agent", [])
    result = await broker.wake_agent(r["agent_id"], message="Hello")
    assert result["status"] == "active"
    assert result["message_queued"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/test_broker/test_broker_core.py::test_broker_wake_agent -v`
Expected: FAIL — `AttributeError: 'Broker' object has no attribute 'wake_agent'`

- [ ] **Step 3: Implement `wake_agent` in Broker core**

Add to `src/broker/core.py` after `resume_agent`:

```python
    async def wake_agent(self, agent_id: str, message: str | None = None) -> dict:
        """Wake a paused/disconnected agent and optionally inject a message.

        Resumes the agent to active status, then if message is provided,
        sends it as a P2P message from the system.
        """
        info = await self._registry.get_info(agent_id)
        if info is None:
            raise ValueError(f"Agent {agent_id} not found")

        if info["status"] != "active":
            await self._registry.resume(agent_id)

        message_queued = False
        if message:
            await self._router.send_message(
                sender_id="system",
                recipient_id=agent_id,
                payload=message,
                msg_type=MessageType.NOTIFICATION,
            )
            message_queued = True

        return {"status": "active", "message_queued": message_queued}
```

Also need to update `_resolve_recipient` in router to handle `"system"` as a special sender. In `src/broker/router.py`, modify `_check_send_permission`:

```python
    async def _check_send_permission(
        self, sender_id: str, squad_id: str | None
    ) -> None:
        """Check that sender is allowed to send in the given squad context."""
        if sender_id == "system":
            return  # System messages bypass permission checks
        if squad_id is None:
            return
        role = await self._squad_store.get_member_role(squad_id, sender_id)
        if role is not None and role == SquadRole.OBSERVER:
            raise PermissionError(
                f"Agent {sender_id} is an observer in squad {squad_id} "
                f"and cannot send messages"
            )
```

- [ ] **Step 4: Add `agent_wake` MCP tool**

Add to `src/mcp_server/server.py` in the Agent Management section:

```python
@mcp.tool()
async def agent_wake(
    agent_id: str,
    message: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Wake a paused/disconnected agent and optionally inject a message. agent_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    result = await broker.wake_agent(agent_id, message)
    # Re-register push callback if context available
    if ctx is not None and result.get("status") == "active":
        callback = _make_push_callback(ctx)
        broker.session_registry.register(agent_id, callback)
    return result
```

- [ ] **Step 5: Run all tests**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/broker/core.py src/broker/router.py src/mcp_server/server.py tests/test_broker/test_broker_core.py
git commit -m "feat: add agent_wake tool for agent-to-agent instance activation"
```

---

### Task 6: Update smoke and system tests

**Files:**
- Modify: `tests/smoke_test.py`
- Modify: `tests/system_test.py`

Add smoke checks for the new tools and verify existing flows still work.

- [ ] **Step 1: Add smoke test checks**

In `tests/smoke_test.py`, add checks for `message_wait` and `agent_wake` tools. The smoke test runs MCP client against the server, so it verifies tool schema availability:

```python
# Add to the tool discovery checks in smoke_test.py:
checks.append(("tool_exists_message_wait", "message_wait" in tool_names))
checks.append(("tool_exists_agent_wake", "agent_wake" in tool_names))
```

- [ ] **Step 2: Add system test for push notification flow**

In `tests/system_test.py`, add a test that verifies the full notification lifecycle:

```python
# Test: push notification is dispatched when message is sent
# 1. Register two agents
# 2. Register a mock notification callback for receiver
# 3. Send message from sender to receiver
# 4. Verify callback was invoked with correct notification data
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Volumes/Data/vibecoding/vibe_agentsquad/agentsquad && uv run pytest tests/ -v`
Expected: All tests pass

Run: `uv run python tests/smoke_test.py`
Expected: All smoke checks pass

Run: `uv run python tests/system_test.py`
Expected: All system checks pass

- [ ] **Step 4: Commit**

```bash
git add tests/smoke_test.py tests/system_test.py
git commit -m "test: add smoke and system tests for push notifications and agent wake"
```

---

### Task 7: Update broker_status and QUICKSTART docs

**Files:**
- Modify: `src/broker/core.py` — enhance `broker_status` to show push session count
- Modify: `QUICKSTART.md` — document push notification, message_wait, agent_wake

- [ ] **Step 1: Enhance broker_status**

```python
    async def broker_status(self) -> dict:
        agents = await self._registry.list_agents()
        active_sessions = sum(
            1 for v in self._sessions.values() if v
        ) if hasattr(self, '_sessions') else 0
        return {
            "status": "healthy" if self._started else "stopped",
            "active_agents": len(agents),
            "push_sessions": len(self.session_registry._sessions),
        }
```

- [ ] **Step 2: Update QUICKSTART.md**

Add section documenting:
- Push notification is automatic when agents register via `agent_register`
- `message_wait` tool for blocking receive
- `agent_wake` tool for activating paused agents
- Fallback to `message_poll` if no active SSE connection

- [ ] **Step 3: Commit**

```bash
git add src/broker/core.py QUICKSTART.md
git commit -m "docs: document push notification, message_wait, and agent_wake in quickstart"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- SessionRegistry with register/unregister/notify: Task 1
- Broker wires SessionRegistry + notification dispatch: Task 2
- MCP server binds push callbacks on register/heartbeat: Task 3
- `message_wait` blocking tool: Task 4
- `agent_wake` instance activation: Task 5
- Smoke + system tests: Task 6
- Docs + status: Task 7

**2. Placeholder scan:** No TBD, TODO, "implement later", "add validation" patterns found. All code blocks contain complete implementation.

**3. Type consistency:**
- `SessionRegistry.register(agent_id: str, callback: NotificationCallback)` — used consistently in Tasks 2, 3, 4, 5
- `NotificationCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]` — consistent across all tasks
- `Broker.session_registry` — public attribute accessed from MCP server layer
- Router return values include `recipient_id` and `subscriber_ids` — used by broker core in Task 2
- `_make_push_callback(ctx)` returns `NotificationCallback` — compatible with SessionRegistry.register()
