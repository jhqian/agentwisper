# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""End-to-end integration tests for agent, squad, and team lifecycle."""

import pytest

from broker.core import Broker
from common.config import BrokerConfig
from common.types import AgentStatus
from persistence.agent_store import AgentStore


@pytest.fixture
async def broker(tmp_path):
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    b = Broker(config)
    await b.start()
    yield b
    await b.stop()


async def test_pause_resume_with_buffered_messages(broker):
    """Paused agent buffers messages, resume delivers them"""
    sender = await broker.register_agent("sender", [])
    receiver = await broker.register_agent("receiver", [])

    await broker.pause_agent(receiver["agent_id"])

    # Send messages while paused
    await broker.send_message(
        sender["agent_id"], receiver["agent_id"], '{"a": 1}', "p2p"
    )
    await broker.send_message(
        sender["agent_id"], receiver["agent_id"], '{"a": 2}', "p2p"
    )

    # Resume should return buffered count
    result = await broker.resume_agent(receiver["agent_id"])
    assert result["buffered_count"] == 2

    # Messages should be pollable
    msgs = await broker.poll_messages(receiver["agent_id"])
    assert len(msgs["messages"]) == 2


async def test_disconnect_reconnect(broker):
    """Agent disconnect, messages buffered, reconnect delivers"""
    sender = await broker.register_agent("sender", [])
    agent = await broker.register_agent("test-agent", [])

    # Simulate disconnect via AgentStore directly
    store = AgentStore(broker._db)
    await store.update_status(agent["agent_id"], AgentStatus.DISCONNECTED)

    # Send message while disconnected
    await broker.send_message(
        sender["agent_id"],
        agent["agent_id"],
        '{"msg": "buffered"}',
        "p2p",
    )

    # Heartbeat restores disconnected agent to active
    await broker.agent_heartbeat(agent["agent_id"])
    info = await broker.get_agent_info(agent["agent_id"])
    assert info["status"] == "active"

    # Buffered messages should be pollable
    msgs = await broker.poll_messages(agent["agent_id"])
    assert len(msgs["messages"]) == 1


async def test_deregister_removes_agent(broker):
    """Deregistered agent is gone"""
    agent = await broker.register_agent("temp-agent", [])
    agent_id = agent["agent_id"]

    await broker.deregister_agent(agent_id)

    info = await broker.get_agent_info(agent_id)
    assert info is None


async def test_squad_full_lifecycle(broker):
    """Create squad -> join -> role change -> dissolve"""
    leader = await broker.register_agent("leader", [])
    member = await broker.register_agent("member", [])
    observer = await broker.register_agent("observer", [])

    # Create
    squad = await broker.create_squad("dev-team", leader["agent_id"])

    # Join
    await broker.join_squad(
        squad["squad_id"], member["agent_id"], "member", leader["agent_id"]
    )
    await broker.join_squad(
        squad["squad_id"],
        observer["agent_id"],
        "observer",
        leader["agent_id"],
    )

    info = await broker.get_squad_info(squad["squad_id"])
    assert len(info["members"]) == 3

    # Role change: promote member to leader (demotes current leader to member)
    await broker.set_squad_role(
        squad["squad_id"], member["agent_id"], "leader", leader["agent_id"]
    )

    # Dissolve (member is now the leader)
    await broker.dissolve_squad(squad["squad_id"], member["agent_id"])

    info = await broker.get_squad_info(squad["squad_id"])
    assert info["squad"]["status"] == "dissolved"


async def test_team_full_lifecycle(broker):
    """Form team -> communicate -> dismiss"""
    a1 = await broker.register_agent("a1", [])
    a2 = await broker.register_agent("a2", [])

    team = await broker.form_team(
        a1["agent_id"], [a1["agent_id"], a2["agent_id"]], topic="review"
    )

    info = await broker.get_team_info(team["team_id"])
    assert len(info["members"]) == 2
    assert info["team"]["topic"] == "review"

    # Dismiss
    await broker.dismiss_team(team["team_id"], a1["agent_id"])

    info = await broker.get_team_info(team["team_id"])
    assert info["team"]["status"] == "dismissed"


async def test_broker_status(broker):
    """Broker reports healthy with correct agent count"""
    await broker.register_agent("a1", [])
    await broker.register_agent("a2", [])

    status = await broker.broker_status()
    assert status["status"] == "healthy"
    assert status["active_agents"] == 2


async def test_heartbeat_updates_timestamp(broker):
    """Heartbeat updates last_heartbeat"""
    agent = await broker.register_agent("test", [])
    result = await broker.agent_heartbeat(agent["agent_id"])
    assert "last_heartbeat" in result
    assert result["status"] == "active"
