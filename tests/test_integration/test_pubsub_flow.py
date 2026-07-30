# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""End-to-end integration tests for pub/sub broadcast flow."""

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


async def test_pubsub_full_flow(broker):
    """Subscribe -> broadcast -> fan-out delivery"""
    publisher = await broker.register_agent("publisher", [])
    sub1 = await broker.register_agent("sub1", [])
    sub2 = await broker.register_agent("sub2", [])

    await broker.subscribe_topic(sub1["agent_id"], "alerts")
    await broker.subscribe_topic(sub2["agent_id"], "alerts")

    result = await broker.broadcast_message(
        publisher["agent_id"],
        "alerts",
        '{"level": "high", "msg": "CPU overload"}',
    )
    assert result["subscriber_count"] == 2

    msgs1 = await broker.poll_messages(sub1["agent_id"])
    assert len(msgs1["messages"]) == 1

    msgs2 = await broker.poll_messages(sub2["agent_id"])
    assert len(msgs2["messages"]) == 1


async def test_pubsub_squad_scoped(broker):
    """Squad-scoped subscriptions"""
    publisher = await broker.register_agent("pub", [])
    sub_squad = await broker.register_agent("sub_squad", [])
    sub_global = await broker.register_agent("sub_global", [])

    # Create squad
    squad = await broker.create_squad("team-a", publisher["agent_id"])
    await broker.join_squad(
        squad["squad_id"], sub_squad["agent_id"], "member", publisher["agent_id"]
    )

    # Squad-scoped subscription
    await broker.subscribe_topic(
        sub_squad["agent_id"], "deploy", squad["squad_id"]
    )
    # Global subscription
    await broker.subscribe_topic(sub_global["agent_id"], "deploy")

    result = await broker.broadcast_message(
        publisher["agent_id"],
        "deploy",
        '{"version": "1.0"}',
        squad_id=squad["squad_id"],
    )
    assert result["subscriber_count"] >= 1

    msgs_squad = await broker.poll_messages(sub_squad["agent_id"])
    assert len(msgs_squad["messages"]) >= 1


async def test_pubsub_unsubscribe(broker):
    """Subscribe, then unsubscribe, verify no delivery"""
    pub = await broker.register_agent("pub", [])
    sub = await broker.register_agent("sub", [])

    sub_result = await broker.subscribe_topic(sub["agent_id"], "events")
    await broker.unsubscribe_topic(sub_result["sub_id"])

    await broker.broadcast_message(pub["agent_id"], "events", "{}")

    msgs = await broker.poll_messages(sub["agent_id"])
    assert len(msgs["messages"]) == 0
