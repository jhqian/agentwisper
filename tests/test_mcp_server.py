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
        agent_deregister,
        agent_info,
        agent_reconnect,
    )

    reg = await agent_register("test", [], ctx=mock_context)
    agent_id = reg["agent_id"]

    result = await agent_deregister(agent_id, ctx=mock_context)
    assert result["status"] == "disconnected"

    # agent_info no longer auto-restores disconnected agents
    info = await agent_info(agent_id, ctx=mock_context)
    assert info["status"] == "disconnected"

    # Must explicitly reconnect
    recon = await agent_reconnect(name="test", agent_id=agent_id, ctx=mock_context)
    assert recon["status"] == "active"


async def test_agent_list_tool(mock_context):
    from mcp_server.server import agent_register, agent_list

    await agent_register("a1", [], ctx=mock_context)
    await agent_register("a2", ["test"], ctx=mock_context)

    result = await agent_list(ctx=mock_context)
    assert len(result["agents"]) == 2


async def test_agent_deregister_tool(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_info, agent_reconnect

    reg = await agent_register("x", [], ctx=mock_context)
    result = await agent_deregister(reg["agent_id"], ctx=mock_context)
    assert result["status"] == "disconnected"
    # agent_info no longer auto-restores
    info = await agent_info(reg["agent_id"], ctx=mock_context)
    assert info["status"] == "disconnected"
    # Reconnect with credentials restores the agent
    recon = await agent_reconnect(name="x", agent_id=reg["agent_id"], ctx=mock_context)
    assert recon["status"] == "active"


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

    with pytest.raises(ValueError, match="never been registered or may have expired"):
        await agent_reconnect("nonexistent", session_name="sess_1", ctx=mock_context)


async def test_agent_reconnect_while_active(mock_context):
    from mcp_server.server import agent_register, agent_reconnect, agent_info

    reg = await agent_register("dev", ["code"], session_name="sess_old", ctx=mock_context)
    # Reconnect without deregistering -- agent is still active
    result = await agent_reconnect("dev", session_name="sess_new", ctx=mock_context)
    assert result["status"] == "active"
    assert result["agent_id"] == reg["agent_id"]
    info = await agent_info(reg["agent_id"], ctx=mock_context)
    assert info["session_name"] == "sess_new"


async def test_agent_reconnect_with_credentials(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_reconnect

    reg = await agent_register("dev", ["code"], session_name="old", ctx=mock_context)
    agent_id = reg["agent_id"]
    await agent_deregister(agent_id, ctx=mock_context)
    result = await agent_reconnect(
        name="dev", agent_id=agent_id, session_name="new", ctx=mock_context
    )
    assert result["status"] == "active"
    assert result["agent_id"] == agent_id


async def test_agent_reconnect_wrong_credentials(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_reconnect

    reg = await agent_register("dev", ["code"], ctx=mock_context)
    await agent_deregister(reg["agent_id"], ctx=mock_context)
    with pytest.raises(Exception):
        await agent_reconnect(
            name="dev", agent_id="agent_wrong", session_name="new", ctx=mock_context
        )


async def test_agent_reconnect_no_agent_id_legacy(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_reconnect

    reg = await agent_register("dev", ["code"], ctx=mock_context)
    await agent_deregister(reg["agent_id"], ctx=mock_context)
    result = await agent_reconnect(name="dev", session_name="new", ctx=mock_context)
    assert result["status"] == "active"


async def test_resolve_agent_session_check(mock_context):
    """_resolve_agent raises ValueError when session_name mismatches."""
    from mcp_server.server import _resolve_agent, _get_broker
    from mcp_server.server import agent_register, agent_reconnect

    broker = _get_broker(mock_context)
    reg = await agent_register("dev", ["code"], session_name="sess_old", ctx=mock_context)
    agent_id = reg["agent_id"]
    # Takeover
    await agent_reconnect(
        name="dev", agent_id=agent_id, session_name="sess_new", ctx=mock_context
    )
    # Resolve with old session_name should fail
    with pytest.raises(ValueError, match="Session invalidated"):
        await _resolve_agent(broker, agent_id, session_name="sess_old")
    # Resolve with new session_name should succeed
    resolved = await _resolve_agent(broker, agent_id, session_name="sess_new")
    assert resolved == agent_id


async def test_resolve_agent_any_status_no_auto_restore(mock_context):
    """_resolve_agent_any_status does NOT auto-restore disconnected agents."""
    from mcp_server.server import _resolve_agent_any_status, _get_broker
    from mcp_server.server import agent_register, agent_deregister

    broker = _get_broker(mock_context)
    reg = await agent_register("dev", ["code"], ctx=mock_context)
    agent_id = reg["agent_id"]
    await agent_deregister(agent_id, ctx=mock_context)
    # Should resolve without error (returns agent_id)
    resolved = await _resolve_agent_any_status(broker, agent_id)
    assert resolved == agent_id
    # But agent should still be disconnected
    info = await broker.get_agent_info(agent_id)
    assert info["status"] == "disconnected"


# ---------------------------------------------------------------------------
# Unified agent-not-found errors
# ---------------------------------------------------------------------------


async def test_resolve_agent_raises_for_nonexistent(mock_context):
    from mcp_server.server import _resolve_agent, message_send

    with pytest.raises(ValueError, match="not found"):
        await _resolve_agent(mock_context.request_context.lifespan_context, "ghost")


async def test_message_send_sender_not_found(mock_context):
    from mcp_server.server import agent_register, message_send

    r = await agent_register("receiver", [], ctx=mock_context)
    with pytest.raises(ValueError, match="not found"):
        await message_send("nonexistent", r["agent_id"], "hello", ctx=mock_context)


async def test_message_poll_agent_not_found(mock_context):
    from mcp_server.server import message_poll

    with pytest.raises(ValueError, match="not found"):
        await message_poll("nonexistent", ctx=mock_context)


async def test_message_wait_agent_not_found(mock_context):
    from mcp_server.server import message_wait

    with pytest.raises(ValueError, match="not found"):
        await message_wait("nonexistent", timeout=0, ctx=mock_context)


async def test_topic_subscribe_agent_not_found(mock_context):
    from mcp_server.server import topic_subscribe

    with pytest.raises(ValueError, match="not found"):
        await topic_subscribe("nonexistent", "alerts", ctx=mock_context)


async def test_agent_info_returns_none_for_nonexistent(mock_context):
    from mcp_server.server import agent_info

    result = await agent_info("nonexistent", ctx=mock_context)
    assert result is None


async def test_agent_deregister_not_found(mock_context):
    from mcp_server.server import agent_deregister

    with pytest.raises(ValueError, match="not found"):
        await agent_deregister("nonexistent", ctx=mock_context)


# ---------------------------------------------------------------------------
# Reconnect: disconnected agents must be explicitly reconnected
# ---------------------------------------------------------------------------


async def test_reconnect_before_message_send(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_reconnect, message_send, agent_info

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("receiver", [], ctx=mock_context)

    # Disconnect sender
    await agent_deregister(r1["agent_id"], ctx=mock_context)

    # Must reconnect before sending
    recon = await agent_reconnect(
        name="sender", agent_id=r1["agent_id"], ctx=mock_context
    )
    assert recon["status"] == "active"

    msg = await message_send(r1["agent_id"], r2["agent_id"], "hello after reconnect", ctx=mock_context)
    assert "msg_id" in msg
    assert msg["status"] == "sent"

    info = await agent_info(r1["agent_id"], ctx=mock_context)
    assert info["status"] == "active"


async def test_reconnect_before_message_poll(mock_context):
    from mcp_server.server import agent_register, message_send, message_poll, agent_deregister, agent_reconnect, agent_info

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("receiver", [], ctx=mock_context)

    # Send a message to r2, then disconnect r2
    await message_send(r1["agent_id"], r2["agent_id"], "pending-msg", ctx=mock_context)
    await agent_deregister(r2["agent_id"], ctx=mock_context)

    # Must reconnect before polling
    recon = await agent_reconnect(
        name="receiver", agent_id=r2["agent_id"], ctx=mock_context
    )
    assert recon["status"] == "active"

    result = await message_poll(r2["agent_id"], ctx=mock_context)
    assert result["count"] >= 1

    info = await agent_info(r2["agent_id"], ctx=mock_context)
    assert info["status"] == "active"


async def test_reconnect_before_subscribe(mock_context):
    from mcp_server.server import agent_register, agent_deregister, agent_reconnect, topic_subscribe, agent_info

    reg = await agent_register("sub", [], ctx=mock_context)
    await agent_deregister(reg["agent_id"], ctx=mock_context)

    # Must reconnect before subscribing
    recon = await agent_reconnect(
        name="sub", agent_id=reg["agent_id"], ctx=mock_context
    )
    assert recon["status"] == "active"

    sub = await topic_subscribe(reg["agent_id"], "alerts", ctx=mock_context)
    assert "sub_id" in sub

    info = await agent_info(reg["agent_id"], ctx=mock_context)
    assert info["status"] == "active"


async def test_reconnect_preserves_squad_after_broker_restart(mock_context):
    """Simulate broker restart: agent marked disconnected, reconnect preserves squad."""
    from mcp_server.server import (
        agent_register, squad_create, squad_join, squad_info, agent_info, agent_reconnect,
    )

    leader = await agent_register("leader", [], ctx=mock_context)
    member = await agent_register("member", [], ctx=mock_context)
    squad = await squad_create("dev-team", leader["agent_id"], ctx=mock_context)
    await squad_join(
        squad["squad_id"], member["agent_id"],
        caller_id=leader["agent_id"], ctx=mock_context,
    )

    # Simulate broker restart by directly disconnecting in DB (no resource cleanup)
    broker = mock_context.request_context.lifespan_context
    from common.types import AgentStatus
    await broker._registry._agent_store.update_status(member["agent_id"], AgentStatus.DISCONNECTED)

    # Reconnect with credentials restores the agent
    recon = await agent_reconnect(
        name="member", agent_id=member["agent_id"], ctx=mock_context
    )
    assert recon["status"] == "active"

    info = await agent_info(member["agent_id"], ctx=mock_context)
    assert info["status"] == "active"
    # Squad membership preserved (was never deregister-cleaned)
    assert info["squad_id"] == squad["squad_id"]


async def test_send_to_disconnected_by_name_buffers(mock_context):
    from mcp_server.server import agent_register, agent_deregister, message_send, message_poll

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("receiver", [], ctx=mock_context)

    await agent_deregister(r2["agent_id"], ctx=mock_context)

    # Sending to a disconnected agent buffers the message
    result = await message_send(r1["agent_id"], "receiver", "hello", ctx=mock_context)
    assert result["status"] == "sent"
    assert result["buffered"] is True

    # Message can be polled after the agent reconnects
    result = await message_poll(r2["agent_id"], ctx=mock_context)
    assert result["count"] >= 1
    assert any(m["payload"] == "hello" for m in result["messages"])


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
    assert msg["status"] == "sent"
    assert msg["recipient_id"] == r2["agent_id"]

    polled = await message_poll(r2["agent_id"], ctx=mock_context)
    assert polled["count"] >= 1
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
    assert result["sent_to"] == 1
    assert "subscriber_ids" not in result

    polled = await message_poll(a2["agent_id"], ctx=mock_context)
    assert polled["count"] >= 1


async def test_message_query_tool(mock_context):
    from mcp_server.server import agent_register, message_send, message_query

    r1 = await agent_register("s", [], ctx=mock_context)
    r2 = await agent_register("r", [], ctx=mock_context)

    await message_send(r1["agent_id"], r2["agent_id"], "msg1", ctx=mock_context)
    await message_send(r1["agent_id"], r2["agent_id"], "msg2", ctx=mock_context)

    result = await message_query(sender=r1["agent_id"], ctx=mock_context)
    assert result["count"] == 2


async def test_message_get_tool(mock_context):
    from mcp_server.server import agent_register, message_send, message_get

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("recver", [], ctx=mock_context)

    sent = await message_send(
        r1["agent_id"], r2["agent_id"], "hello", ctx=mock_context
    )
    msg_id = sent["msg_id"]

    result = await message_get(msg_id, ctx=mock_context)
    assert result["message"] is not None
    assert result["message"]["msg_id"] == msg_id
    assert result["message"]["payload"] == "hello"

    not_found = await message_get("msg_nonexistent", ctx=mock_context)
    assert not_found["message"] is None


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

    assert result["count"] >= 1
    assert result["waited"] is True
    assert result["messages"][0]["payload"] == "delayed hello"


async def test_message_wait_returns_immediately_if_pending(mock_context):
    from mcp_server.server import agent_register, message_send, message_wait

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("receiver", [], ctx=mock_context)

    await message_send(r1["agent_id"], r2["agent_id"], "hello", ctx=mock_context)

    result = await message_wait(r2["agent_id"], timeout=5, ctx=mock_context)
    assert result["count"] >= 1
    assert result["waited"] is False


async def test_message_wait_timeout(mock_context):
    from mcp_server.server import agent_register, message_wait

    r = await agent_register("lonely", [], ctx=mock_context)

    result = await message_wait(r["agent_id"], timeout=1, ctx=mock_context)
    assert result["count"] == 0
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


def test_run_server_sets_host_and_port():
    from unittest.mock import AsyncMock, patch

    from mcp_server.server import run_server

    with patch("uvicorn.Server") as mock_server_cls, \
         patch("uvicorn.Config") as mock_config_cls:
        mock_server = mock_server_cls.return_value
        mock_server.serve = AsyncMock()
        run_server(port=9000, host="0.0.0.0")
        mock_config_cls.assert_called_once()
        config_kwargs = mock_config_cls.call_args.kwargs
        assert config_kwargs["host"] == "0.0.0.0"
        assert config_kwargs["port"] == 9000
        assert config_kwargs["timeout_graceful_shutdown"] == 5
        mock_server.serve.assert_called_once()


async def test_message_send_with_client_msg_id(mock_context):
    from mcp_server.server import agent_register, message_send, message_get

    r1 = await agent_register("sender", [], ctx=mock_context)
    r2 = await agent_register("recver", [], ctx=mock_context)

    result = await message_send(
        r1["agent_id"], r2["agent_id"], "hello",
        msg_id="msg_clienttest123", ctx=mock_context,
    )
    assert result["msg_id"] == "msg_clienttest123"
    assert result["status"] == "sent"

    retrieved = await message_get("msg_clienttest123", ctx=mock_context)
    assert retrieved["message"] is not None
    assert retrieved["message"]["payload"] == "hello"


async def test_message_broadcast_with_client_msg_id(mock_context):
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
        a1["agent_id"], "events", '{"event": "test"}',
        msg_id="msg_bcast_client456", ctx=mock_context,
    )
    assert result["msg_id"] == "msg_bcast_client456"
    assert result["sent_to"] == 1

    polled = await message_poll(a2["agent_id"], ctx=mock_context)
    assert polled["count"] >= 1
