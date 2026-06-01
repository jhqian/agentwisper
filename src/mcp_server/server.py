# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""MCP Server exposing all broker operations as MCP tools via FastMCP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP, Context

from broker.core import Broker
from common.config import BrokerConfig, load_config
from persistence.message_store import MessageStore

# Module-level singleton broker shared across all MCP sessions.
# The FastMCP lifespan is invoked once per client session (not once per
# server), so we cannot rely on it to hold a single Broker. Instead we
# create one Broker the first time it is needed and reuse it.
_broker: Broker | None = None

# ---------------------------------------------------------------------------
# Lightweight message transformation (MCP boundary)
# ---------------------------------------------------------------------------

_PAYLOAD_THRESHOLD = 500
_PREVIEW_LENGTH = 200


def _lightweight_message(msg: dict) -> dict:
    """Transform a full message record into a token-efficient format.

    Short payloads (<=500 chars) are returned in full. Longer payloads
    are truncated to a 200-char preview. Null optional fields are omitted.
    """
    result = {
        "msg_id": msg["msg_id"],
        "sender_id": msg.get("sender_id"),
        "msg_type": msg.get("msg_type"),
    }

    payload = msg.get("payload", "")
    if len(payload) <= _PAYLOAD_THRESHOLD:
        result["payload"] = payload
    else:
        result["payload_preview"] = payload[:_PREVIEW_LENGTH] + "..."

    for key in ("topic", "squad_id", "parent_msg_id"):
        value = msg.get(key)
        if value is not None:
            result[key] = value

    return result


async def _get_or_create_broker() -> Broker:
    global _broker
    if _broker is None:
        config = load_config()
        _broker = Broker(config)
        await _broker.start()
    return _broker


@asynccontextmanager
async def broker_lifespan(app: FastMCP):
    """Lifespan context manager that yields the shared Broker singleton.

    The Broker is created on first access and reused across sessions.
    It is only torn down when the process exits.
    """
    broker = await _get_or_create_broker()
    yield broker


mcp = FastMCP(
    name="agentsquad-broker",
    lifespan=broker_lifespan,
)


def _get_broker(ctx: Context) -> Broker:
    return ctx.request_context.lifespan_context


async def _try_restore_agent(broker: Broker, agent_id_or_name: str) -> str | None:
    """Try to restore a disconnected agent and return its agent_id.

    Returns agent_id if restored, None if agent not found or already active.
    """
    # Try by agent_id first
    agent = await broker._registry.get_info(agent_id_or_name)
    if agent is None:
        # Try by name
        agent = await broker._registry._agent_store.get_by_name(agent_id_or_name)
    if agent is None:
        return None
    if agent["status"] != "disconnected":
        return None
    # Auto-reconnect
    result = await broker.reconnect_agent(agent["name"])
    return result["agent_id"]


async def _resolve_agent(broker: Broker, agent_id_or_name: str) -> str:
    """Resolve agent_id or name to agent_id.

    If the agent is disconnected, automatically restores it via reconnect.
    Raises ValueError if agent not found.
    """
    resolved = await broker._registry.resolve_recipient(agent_id_or_name)
    if resolved is not None:
        return resolved
    # Agent exists but may be disconnected — try auto-restore
    restored = await _try_restore_agent(broker, agent_id_or_name)
    if restored is not None:
        return restored
    raise ValueError(
        f"Agent '{agent_id_or_name}' not found or is disconnected"
    )


async def _resolve_agent_any_status(broker: Broker, agent_id_or_name: str) -> str:
    """Resolve agent_id or name, auto-restoring disconnected agents.

    Raises ValueError if agent not found.
    """
    # Try by agent_id first
    agent = await broker._registry.get_info(agent_id_or_name)
    if agent is not None:
        if agent["status"] == "disconnected":
            result = await broker.reconnect_agent(agent["name"])
            return result["agent_id"]
        return agent["agent_id"]
    # Try by name
    agent = await broker._registry._agent_store.get_by_name(agent_id_or_name)
    if agent is not None:
        if agent["status"] == "disconnected":
            result = await broker.reconnect_agent(agent["name"])
            return result["agent_id"]
        return agent["agent_id"]
    raise ValueError(f"Agent '{agent_id_or_name}' not found")




# ---------------------------------------------------------------------------
# Agent Management
# ---------------------------------------------------------------------------


@mcp.tool()
async def agent_register(
    name: str,
    capabilities: list[str],
    metadata: dict[str, Any] | None = None,
    session_name: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Register a new agent.

    If the requested name is already taken by an active agent,
    a numeric suffix is appended (e.g. "dev" -> "dev-1").
    Returns agent_id, assigned_name, and status.
    """
    broker = _get_broker(ctx)
    return await broker.register_agent(name, capabilities, metadata, session_name=session_name)


@mcp.tool()
async def agent_deregister(agent_id: str, ctx: Context | None = None) -> dict:
    """Remove an agent. Accepts agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent_any_status(broker, agent_id)
    return await broker.deregister_agent(agent_id)


@mcp.tool()
async def agent_info(agent_id: str, ctx: Context | None = None) -> dict | None:
    """Get agent details. Accepts agent_id or name. Returns None if not found."""
    broker = _get_broker(ctx)
    try:
        agent_id = await _resolve_agent_any_status(broker, agent_id)
    except ValueError:
        return None
    return await broker.get_agent_info(agent_id)


@mcp.tool()
async def agent_list(squad_id: str | None = None, ctx: Context | None = None) -> dict:
    """List agents, optionally filtered by squad."""
    broker = _get_broker(ctx)
    return await broker.list_agents(squad_id)


@mcp.tool()
async def agent_reconnect(
    name: str,
    session_name: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Reconnect a previously disconnected agent by name.

    Restores the agent to active status with its original agent_id.
    All squad memberships, subscriptions, and buffered messages are preserved.
    """
    broker = _get_broker(ctx)
    return await broker.reconnect_agent(name, session_name=session_name)


# ---------------------------------------------------------------------------
# Squad Management
# ---------------------------------------------------------------------------


@mcp.tool()
async def squad_create(
    name: str,
    caller_id: str,
    metadata: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> dict:
    """Create a new squad. Creator becomes leader. caller_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    caller_id = await _resolve_agent(broker, caller_id)
    return await broker.create_squad(name, caller_id, metadata)


@mcp.tool()
async def squad_dissolve(
    squad_id: str, caller_id: str, ctx: Context | None = None
) -> dict:
    """Dissolve a squad (leader only). caller_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    caller_id = await _resolve_agent(broker, caller_id)
    return await broker.dissolve_squad(squad_id, caller_id)


@mcp.tool()
async def squad_join(
    squad_id: str,
    agent_id: str,
    role: str = "member",
    caller_id: str = "",
    ctx: Context | None = None,
) -> dict:
    """Add agent to squad (leader only). agent_id and caller_id accept agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    caller_id = await _resolve_agent(broker, caller_id)
    return await broker.join_squad(squad_id, agent_id, role, caller_id)


@mcp.tool()
async def squad_leave(agent_id: str, ctx: Context | None = None) -> dict:
    """Leave current squad (any member). Accepts agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent_any_status(broker, agent_id)
    return await broker.leave_squad(agent_id)


@mcp.tool()
async def squad_kick(
    squad_id: str, agent_id: str, caller_id: str, ctx: Context | None = None
) -> dict:
    """Remove member from squad (leader only). agent_id and caller_id accept agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    caller_id = await _resolve_agent(broker, caller_id)
    return await broker.kick_from_squad(squad_id, agent_id, caller_id)


@mcp.tool()
async def squad_set_role(
    squad_id: str, agent_id: str, new_role: str, caller_id: str,
    ctx: Context | None = None,
) -> dict:
    """Change member role (leader only). agent_id and caller_id accept agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    caller_id = await _resolve_agent(broker, caller_id)
    return await broker.set_squad_role(squad_id, agent_id, new_role, caller_id)


@mcp.tool()
async def squad_info(squad_id: str, ctx: Context | None = None) -> dict:
    """Get squad details with member list."""
    broker = _get_broker(ctx)
    return await broker.get_squad_info(squad_id)


@mcp.tool()
async def squad_list(ctx: Context | None = None) -> dict:
    """List all active squads."""
    broker = _get_broker(ctx)
    return await broker.list_squads()


# ---------------------------------------------------------------------------
# Ad-hoc Team
# ---------------------------------------------------------------------------


@mcp.tool()
async def team_form(
    agent_ids: list[str],
    topic: str | None = None,
    ttl_seconds: int | None = None,
    ctx: Context | None = None,
) -> dict:
    """Form an ad-hoc team. agent_ids accept agent_id or name."""
    broker = _get_broker(ctx)
    if not agent_ids:
        return {"error": "agent_ids cannot be empty"}
    resolved_ids = [await _resolve_agent(broker, aid) for aid in agent_ids]
    return await broker.form_team(resolved_ids[0], resolved_ids, topic, ttl_seconds)


@mcp.tool()
async def team_dismiss(
    team_id: str, caller_id: str, ctx: Context | None = None
) -> dict:
    """Dismiss an ad-hoc team (any member). caller_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    caller_id = await _resolve_agent(broker, caller_id)
    return await broker.dismiss_team(team_id, caller_id)


@mcp.tool()
async def team_info(team_id: str, ctx: Context | None = None) -> dict:
    """Get team details with member list."""
    broker = _get_broker(ctx)
    return await broker.get_team_info(team_id)


@mcp.tool()
async def team_list(
    agent_id: str | None = None, ctx: Context | None = None
) -> dict:
    """List active teams, optionally filtered by agent. agent_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    if agent_id:
        agent_id = await _resolve_agent(broker, agent_id)
    return await broker.list_teams(agent_id)


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


@mcp.tool()
async def message_send(
    sender_id: str,
    recipient: str,
    payload: str,
    msg_type: str = "p2p",
    squad_id: str | None = None,
    msg_id: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Send a P2P or RPC message. sender_id and recipient accept agent_id or name."""
    broker = _get_broker(ctx)
    sender_id = await _resolve_agent(broker, sender_id)
    result = await broker.send_message(sender_id, recipient, payload, msg_type, squad_id, msg_id=msg_id)
    return {"msg_id": result["msg_id"], "status": "sent"}


@mcp.tool()
async def message_broadcast(
    sender_id: str,
    topic: str,
    payload: str,
    squad_id: str | None = None,
    msg_id: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Publish to topic subscribers. sender_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    sender_id = await _resolve_agent(broker, sender_id)
    result = await broker.broadcast_message(sender_id, topic, payload, squad_id, msg_id=msg_id)
    return {"msg_id": result["msg_id"], "sent_to": result["subscriber_count"]}



@mcp.tool()
async def message_poll(
    agent_id: str,
    limit: int = 50,
    unread_only: bool = True,
    ctx: Context | None = None,
) -> dict:
    """Pull pending messages for agent. agent_id accepts agent_id or name.

    Args:
        agent_id: Agent to poll for. Accepts agent_id or name.
        limit: Max messages to return.
        unread_only: Only return unread messages.
    """
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    result = await broker.poll_messages(agent_id, limit, unread_only)
    msgs = [_lightweight_message(m) for m in result.get("messages", [])]
    return {"messages": msgs, "count": len(msgs)}


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

    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)

    result = await broker.poll_messages(agent_id, limit, unread_only=True)
    msgs = [_lightweight_message(m) for m in result.get("messages", [])]
    if msgs:
        return {"messages": msgs, "count": len(msgs), "waited": False}

    if timeout <= 0:
        return {"messages": [], "count": 0, "waited": False}

    event = broker.register_wait(agent_id)
    try:
        with anyio.fail_after(timeout):
            await event.wait()
        waited = True
    except TimeoutError:
        waited = False
    finally:
        broker.unregister_wait(agent_id)

    result = await broker.poll_messages(agent_id, limit, unread_only=True)
    msgs = [_lightweight_message(m) for m in result.get("messages", [])]
    return {"messages": msgs, "count": len(msgs), "waited": waited}


@mcp.tool()
async def message_query(
    sender: str | None = None,
    recipient: str | None = None,
    topic: str | None = None,
    msg_type: str | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    limit: int = 50,
    ctx: Context | None = None,
) -> dict:
    """Query message history."""
    broker = _get_broker(ctx)
    store = MessageStore(broker._db)
    messages = await store.query(
        sender_id=sender,
        recipient_id=recipient,
        topic=topic,
        msg_type=msg_type,
        time_start=time_start,
        time_end=time_end,
        limit=limit,
    )
    msgs = [_lightweight_message(m) for m in messages]
    return {"messages": msgs, "count": len(msgs)}


@mcp.tool()
async def message_get(
    msg_id: str,
    ctx: Context | None = None,
) -> dict:
    """Retrieve a single message by its msg_id. Returns the full message record or None if not found."""
    from persistence.message_store import MessageStore

    broker = _get_broker(ctx)
    store = MessageStore(broker._db)
    message = await store.get(msg_id)
    return {"message": message}


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------


@mcp.tool()
async def topic_subscribe(
    agent_id: str,
    topic: str,
    squad_id: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Subscribe to topic. agent_id accepts agent_id or name."""
    broker = _get_broker(ctx)
    agent_id = await _resolve_agent(broker, agent_id)
    return await broker.subscribe_topic(agent_id, topic, squad_id)


@mcp.tool()
async def topic_unsubscribe(sub_id: str, ctx: Context | None = None) -> dict:
    """Unsubscribe from topic."""
    broker = _get_broker(ctx)
    return await broker.unsubscribe_topic(sub_id)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@mcp.tool()
async def broker_status(ctx: Context | None = None) -> dict:
    """Get broker health, agent count, queue depth."""
    broker = _get_broker(ctx)
    return await broker.broker_status()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def create_server() -> FastMCP:
    """Factory function for creating the MCP server."""
    return mcp


def run_server(port: int = 8000, host: str = "127.0.0.1") -> None:
    """Run the MCP server with streamable-http transport."""
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    mcp.settings.port = port
    mcp.settings.host = host
    mcp.run(transport="streamable-http")
