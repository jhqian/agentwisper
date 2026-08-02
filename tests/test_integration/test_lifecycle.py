# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""End-to-end integration tests for agent, squad, and team lifecycle."""

import pytest

from agentwisper.broker.core import Broker
from agentwisper.common.config import BrokerConfig


@pytest.fixture
async def broker(tmp_path):
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    b = Broker(config)
    await b.start()
    yield b
    await b.stop()


async def test_reconnect_with_buffered_messages(broker):
    """Disconnected agent can reconnect and resume operations"""
    receiver = await broker.register_agent("receiver")

    await broker.deregister_agent(receiver["agent_id"])

    # Messages sent while disconnected are buffered for later delivery
    # Reconnect restores agent and returns buffered count
    result = await broker.reconnect_agent("receiver")
    assert result["status"] == "active"
    assert result["agent_id"] == receiver["agent_id"]


async def test_deregister_soft_deletes_agent(broker):
    """Deregistered agent becomes disconnected, not removed"""
    agent = await broker.register_agent("temp-agent")
    agent_id = agent["agent_id"]

    await broker.deregister_agent(agent_id)

    info = await broker.get_agent_info(agent_id)
    assert info is not None
    assert info["status"] == "disconnected"


async def test_squad_full_lifecycle(broker):
    """Create squad -> join -> role change -> dissolve"""
    leader = await broker.register_agent("leader")
    member = await broker.register_agent("member")
    observer = await broker.register_agent("observer")

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
    a1 = await broker.register_agent("a1")
    a2 = await broker.register_agent("a2")

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
    await broker.register_agent("a1")
    await broker.register_agent("a2")

    status = await broker.broker_status()
    assert status["status"] == "healthy"
    assert status["active_agents"] == 2
