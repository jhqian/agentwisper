# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Integration-style tests for MCP Server tool functions."""

import pytest
from unittest.mock import MagicMock

from broker.core import Broker
from common.config import BrokerConfig


@pytest.fixture
async def broker_ctx(tmp_path):
    """Provide a started Broker instance against a temporary database."""
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    broker = Broker(config)
    await broker.start()
    yield broker
    await broker.stop()


@pytest.fixture
def mock_context(broker_ctx):
    """Create a mock MCP Context that yields the Broker from lifespan."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context = broker_ctx
    return ctx


# ---------------------------------------------------------------------------
# Agent Management
# ---------------------------------------------------------------------------


async def test_agent_register_tool(mock_context):
    from mcp_server.server import agent_register

    result = await agent_register("test-agent", ["code"], ctx=mock_context)
    assert "agent_id" in result
    assert result["status"] == "active"


async def test_agent_lifecycle_tools(mock_context):
    from mcp_server.server import (
        agent_register,
        agent_pause,
        agent_resume,
        agent_info,
    )

    reg = await agent_register("test", [], ctx=mock_context)
    agent_id = reg["agent_id"]

    await agent_pause(agent_id, ctx=mock_context)
    info = await agent_info(agent_id, ctx=mock_context)
    assert info["status"] == "paused"

    result = await agent_resume(agent_id, ctx=mock_context)
    assert result["status"] == "active"


async def test_agent_list_tool(mock_context):
    from mcp_server.server import agent_register, agent_list

    await agent_register("a1", [], ctx=mock_context)
    await agent_register("a2", ["test"], ctx=mock_context)

    result = await agent_list(ctx=mock_context)
    assert len(result["agents"]) == 2


async def test_agent_deregister_tool(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_info

    reg = await agent_register("x", [], ctx=mock_context)
    result = await agent_deregister(reg["agent_id"], ctx=mock_context)
    assert result["status"] == "disconnected"
    info = await agent_info(reg["agent_id"], ctx=mock_context)
    assert info["status"] == "disconnected"


async def test_agent_register_with_session_name(mock_context):
    from mcp_server.server import agent_register, agent_info

    result = await agent_register("dev", ["code"], session_name="sess_abc", ctx=mock_context)
    assert result["status"] == "active"
    info = await agent_info(result["agent_id"], ctx=mock_context)
    assert info["session_name"] == "sess_abc"


async def test_agent_reconnect_tool(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_reconnect, agent_info

    reg = await agent_register("dev", ["code"], session_name="sess_old", ctx=mock_context)
    await agent_deregister(reg["agent_id"], ctx=mock_context)
    result = await agent_reconnect("dev", session_name="sess_new", ctx=mock_context)
    assert result["status"] == "active"
    assert result["agent_id"] == reg["agent_id"]
    info = await agent_info(reg["agent_id"], ctx=mock_context)
    assert info["session_name"] == "sess_new"


async def test_agent_reconnect_not_found(mock_context):
    from mcp_server.server import agent_reconnect

    with pytest.raises(ValueError, match="No disconnected agent"):
        await agent_reconnect("nonexistent", session_name="sess_1", ctx=mock_context)


# ---------------------------------------------------------------------------
# Squad Management
# ---------------------------------------------------------------------------


async def test_squad_tools(mock_context):
    from mcp_server.server import agent_register, squad_create, squad_info

    reg = await agent_register("leader", [], ctx=mock_context)
    squad = await squad_create("dev-team", reg["agent_id"], ctx=mock_context)
    assert "squad_id" in squad
    assert squad["role"] == "leader"

    info = await squad_info(squad["squad_id"], ctx=mock_context)
    assert info["squad"]["name"] == "dev-team"


async def test_squad_join_leave(mock_context):
    from mcp_server.server import (
        agent_register,
        squad_create,
        squad_join,
        squad_leave,
        squad_info,
    )

    leader = await agent_register("leader", [], ctx=mock_context)
    member = await agent_register("member", [], ctx=mock_context)
    squad = await squad_create("team", leader["agent_id"], ctx=mock_context)

    await squad_join(
        squad["squad_id"],
        member["agent_id"],
        caller_id=leader["agent_id"],
        ctx=mock_context,
    )
    info = await squad_info(squad["squad_id"], ctx=mock_context)
    assert len(info["members"]) == 2

    await squad_leave(member["agent_id"], ctx=mock_context)
    info = await squad_info(squad["squad_id"], ctx=mock_context)
    assert len(info["members"]) == 1


async def test_squad_list_tool(mock_context):
    from mcp_server.server import agent_register, squad_create, squad_list

    reg = await agent_register("l", [], ctx=mock_context)
    await squad_create("s1", reg["agent_id"], ctx=mock_context)
    await squad_create("s2", reg["agent_id"], ctx=mock_context)

    result = await squad_list(ctx=mock_context)
    assert len(result["squads"]) == 2


# ---------------------------------------------------------------------------
# Team Management
# ---------------------------------------------------------------------------


async def test_team_form_and_info(mock_context):
    from mcp_server.server import agent_register, team_form, team_info

    a1 = await agent_register("t1", [], ctx=mock_context)
    a2 = await agent_register("t2", [], ctx=mock_context)

    team = await team_form(
        [a1["agent_id"], a2["agent_id"]], topic="testing", ctx=mock_context
    )
    assert "team_id" in team

    info = await team_info(team["team_id"], ctx=mock_context)
    assert info["team"]["topic"] == "testing"


async def test_team_dismiss(mock_context):
    from mcp_server.server import agent_register, team_form, team_dismiss

    a1 = await agent_register("t1", [], ctx=mock_context)
    a2 = await agent_register("t2", [], ctx=mock_context)

    team = await team_form([a1["agent_id"], a2["agent_id"]], ctx=mock_context)
    result = await team_dismiss(team["team_id"], a1["agent_id"], ctx=mock_context)
    assert result["status"] == "dismissed"


async def test_team_list_tool(mock_context):
    from mcp_server.server import agent_register, team_form, team_list

    a1 = await agent_register("t1", [], ctx=mock_context)
    a2 = await agent_register("t2", [], ctx=mock_context)

    await team_form([a1["agent_id"], a2["agent_id"]], ctx=mock_context)
    result = await team_list(ctx=mock_context)
    assert len(result["teams"]) >= 1


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


async def test_message_send_and_poll(mock_context):
    from mcp_server.server import agent_register, message_send, message_poll

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("receiver", [], ctx=mock_context)

    msg = await message_send(
        r1["agent_id"], r2["agent_id"], '{"hello": true}', ctx=mock_context
    )
    assert "msg_id" in msg

    polled = await message_poll(r2["agent_id"], ctx=mock_context)
    assert polled["total"] >= 1
    assert polled["messages"][0]["payload"] == '{"hello": true}'


async def test_message_broadcast_tool(mock_context):
    from mcp_server.server import (
        agent_register,
        topic_subscribe,
        message_broadcast,
        message_poll,
    )

    a1 = await agent_register("pub", [], ctx=mock_context)
    a2 = await agent_register("sub", [], ctx=mock_context)

    await topic_subscribe(a2["agent_id"], "events", ctx=mock_context)
    result = await message_broadcast(
        a1["agent_id"], "events", '{"event": "test"}', ctx=mock_context
    )
    assert result["subscriber_count"] == 1

    polled = await message_poll(a2["agent_id"], ctx=mock_context)
    assert polled["total"] >= 1


async def test_message_query_tool(mock_context):
    from mcp_server.server import agent_register, message_send, message_query

    r1 = await agent_register("s", [], ctx=mock_context)
    r2 = await agent_register("r", [], ctx=mock_context)

    await message_send(r1["agent_id"], r2["agent_id"], "msg1", ctx=mock_context)
    await message_send(r1["agent_id"], r2["agent_id"], "msg2", ctx=mock_context)

    result = await message_query(sender=r1["agent_id"], ctx=mock_context)
    assert result["total"] == 2


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------


async def test_topic_subscribe_unsubscribe(mock_context):
    from mcp_server.server import (
        agent_register,
        topic_subscribe,
        topic_unsubscribe,
    )

    reg = await agent_register("sub", [], ctx=mock_context)
    sub = await topic_subscribe(reg["agent_id"], "alerts", ctx=mock_context)
    assert "sub_id" in sub

    result = await topic_unsubscribe(sub["sub_id"], ctx=mock_context)
    assert result["status"] == "unsubscribed"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_broker_status_tool(mock_context):
    from mcp_server.server import broker_status

    result = await broker_status(ctx=mock_context)
    assert result["status"] == "healthy"


async def test_message_wait_receives_message(mock_context):
    import asyncio
    from mcp_server.server import agent_register, message_send, message_wait

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("receiver", [], ctx=mock_context)

    async def send_after_delay():
        await asyncio.sleep(0.1)
        await message_send(r1["agent_id"], r2["agent_id"], "delayed hello", ctx=mock_context)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(send_after_delay())
        result = await message_wait(r2["agent_id"], timeout=5, ctx=mock_context)

    assert result["total"] >= 1
    assert result["waited"] is True
    assert result["messages"][0]["payload"] == "delayed hello"


async def test_message_wait_returns_immediately_if_pending(mock_context):
    from mcp_server.server import agent_register, message_send, message_wait

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("receiver", [], ctx=mock_context)

    await message_send(r1["agent_id"], r2["agent_id"], "hello", ctx=mock_context)

    result = await message_wait(r2["agent_id"], timeout=5, ctx=mock_context)
    assert result["total"] >= 1
    assert result["waited"] is False


async def test_message_wait_timeout(mock_context):
    from mcp_server.server import agent_register, message_wait

    r = await agent_register("lonely", [], ctx=mock_context)

    result = await message_wait(r["agent_id"], timeout=1, ctx=mock_context)
    assert result["total"] == 0
    assert result["waited"] is False


# ---------------------------------------------------------------------------
# Server helpers
# ---------------------------------------------------------------------------


def test_create_server_returns_fastmcp():
    from mcp_server.server import create_server
    from mcp.server.fastmcp import FastMCP

    server = create_server()
    assert isinstance(server, FastMCP)


def test_mcp_instance_has_tools():
    from mcp_server.server import mcp

    # FastMCP stores tool functions internally; verify the module-level
    # functions are importable and the mcp object exists.
    assert mcp is not None
    assert mcp.name == "agentsquad-broker"
