# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""MCP Server exposing all broker operations as MCP tools via FastMCP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP, Context

from broker.core import Broker
from common.config import BrokerConfig, load_config
from persistence.message_store import MessageStore


@asynccontextmanager
async def broker_lifespan(app: FastMCP):
    """Lifespan context manager that creates and tears down the Broker."""
    config = load_config()
    broker = Broker(config)
    await broker.start()
    yield broker
    await broker.stop()


mcp = FastMCP(
    name="vibe-agentsquad",
    lifespan=broker_lifespan,
)


def _get_broker(ctx: Context) -> Broker:
    return ctx.request_context.lifespan_context


# ---------------------------------------------------------------------------
# Agent Management
# ---------------------------------------------------------------------------


@mcp.tool()
async def agent_register(
    name: str,
    capabilities: list[str],
    metadata: dict[str, Any] | None = None,
    ctx: Context | None = None,
) -> dict:
    """Register a new agent. Returns agent_id and status."""
    broker = _get_broker(ctx)
    return await broker.register_agent(name, capabilities, metadata)


@mcp.tool()
async def agent_deregister(agent_id: str, ctx: Context | None = None) -> dict:
    """Remove an agent. Marks undelivered messages as orphaned."""
    broker = _get_broker(ctx)
    return await broker.deregister_agent(agent_id)


@mcp.tool()
async def agent_pause(agent_id: str, ctx: Context | None = None) -> dict:
    """Pause an agent. Messages are buffered until resume."""
    broker = _get_broker(ctx)
    return await broker.pause_agent(agent_id)


@mcp.tool()
async def agent_resume(agent_id: str, ctx: Context | None = None) -> dict:
    """Resume a paused agent. Returns buffered message count."""
    broker = _get_broker(ctx)
    return await broker.resume_agent(agent_id)


@mcp.tool()
async def agent_info(agent_id: str, ctx: Context | None = None) -> dict | None:
    """Get agent details."""
    broker = _get_broker(ctx)
    return await broker.get_agent_info(agent_id)


@mcp.tool()
async def agent_list(squad_id: str | None = None, ctx: Context | None = None) -> dict:
    """List agents, optionally filtered by squad."""
    broker = _get_broker(ctx)
    return await broker.list_agents(squad_id)


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
    """Create a new squad. Creator becomes leader."""
    broker = _get_broker(ctx)
    return await broker.create_squad(name, caller_id, metadata)


@mcp.tool()
async def squad_dissolve(
    squad_id: str, caller_id: str, ctx: Context | None = None
) -> dict:
    """Dissolve a squad (leader only). Members become freelance."""
    broker = _get_broker(ctx)
    return await broker.dissolve_squad(squad_id, caller_id)


@mcp.tool()
async def squad_join(
    squad_id: str,
    agent_id: str,
    role: str = "member",
    caller_id: str = "",
    ctx: Context | None = None,
) -> dict:
    """Add agent to squad (leader only)."""
    broker = _get_broker(ctx)
    return await broker.join_squad(squad_id, agent_id, role, caller_id)


@mcp.tool()
async def squad_leave(agent_id: str, ctx: Context | None = None) -> dict:
    """Leave current squad (any member)."""
    broker = _get_broker(ctx)
    return await broker.leave_squad(agent_id)


@mcp.tool()
async def squad_kick(
    squad_id: str, agent_id: str, caller_id: str, ctx: Context | None = None
) -> dict:
    """Remove member from squad (leader only)."""
    broker = _get_broker(ctx)
    return await broker.kick_from_squad(squad_id, agent_id, caller_id)


@mcp.tool()
async def squad_set_role(
    squad_id: str, agent_id: str, new_role: str, caller_id: str,
    ctx: Context | None = None,
) -> dict:
    """Change member role (leader only)."""
    broker = _get_broker(ctx)
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
    """Form an ad-hoc team. Initiator is the first agent in agent_ids."""
    broker = _get_broker(ctx)
    if not agent_ids:
        return {"error": "agent_ids cannot be empty"}
    return await broker.form_team(agent_ids[0], agent_ids, topic, ttl_seconds)


@mcp.tool()
async def team_dismiss(
    team_id: str, caller_id: str, ctx: Context | None = None
) -> dict:
    """Dismiss an ad-hoc team (any member)."""
    broker = _get_broker(ctx)
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
    """List active teams, optionally filtered by agent."""
    broker = _get_broker(ctx)
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
    ctx: Context | None = None,
) -> dict:
    """Send a P2P or RPC message. Recipient accepts agent_id or name."""
    broker = _get_broker(ctx)
    return await broker.send_message(sender_id, recipient, payload, msg_type, squad_id)


@mcp.tool()
async def message_broadcast(
    sender_id: str,
    topic: str,
    payload: str,
    squad_id: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Publish to topic subscribers."""
    broker = _get_broker(ctx)
    return await broker.broadcast_message(sender_id, topic, payload, squad_id)


@mcp.tool()
async def message_reply(
    parent_msg_id: str,
    sender_id: str,
    payload: str,
    ctx: Context | None = None,
) -> dict:
    """Reply to an RPC request."""
    broker = _get_broker(ctx)
    return await broker.reply_message(parent_msg_id, sender_id, payload)


@mcp.tool()
async def message_poll(
    agent_id: str,
    limit: int = 50,
    unread_only: bool = True,
    ctx: Context | None = None,
) -> dict:
    """Pull pending messages for agent."""
    broker = _get_broker(ctx)
    result = await broker.poll_messages(agent_id, limit, unread_only)
    # Broker returns {"messages": [...]} -- add total count
    msgs = result.get("messages", [])
    return {"messages": msgs, "total": len(msgs)}


@mcp.tool()
async def message_ack(msg_id: str, ctx: Context | None = None) -> dict:
    """Acknowledge message delivery."""
    broker = _get_broker(ctx)
    return await broker.acknowledge_message(msg_id)


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
    return {"messages": messages, "total": len(messages)}


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
    """Subscribe to topic."""
    broker = _get_broker(ctx)
    return await broker.subscribe_topic(agent_id, topic, squad_id)


@mcp.tool()
async def topic_unsubscribe(sub_id: str, ctx: Context | None = None) -> dict:
    """Unsubscribe from topic."""
    broker = _get_broker(ctx)
    return await broker.unsubscribe_topic(sub_id)


# ---------------------------------------------------------------------------
# Heartbeat & Health
# ---------------------------------------------------------------------------


@mcp.tool()
async def heartbeat(agent_id: str, ctx: Context | None = None) -> dict:
    """Signal agent is alive."""
    broker = _get_broker(ctx)
    return await broker.agent_heartbeat(agent_id)


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


def run_server(transport: str = "stdio") -> None:
    """Run the MCP server."""
    mcp.run(transport=transport)
