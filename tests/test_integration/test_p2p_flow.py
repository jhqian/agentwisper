# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""End-to-end integration tests for P2P message flow."""

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


async def test_p2p_full_flow(broker):
    """Register -> send -> poll -> ack"""
    sender = await broker.register_agent("alice", ["code"])
    receiver = await broker.register_agent("bob", ["review"])

    msg = await broker.send_message(
        sender["agent_id"],
        receiver["agent_id"],
        '{"question": "What is the DB schema?"}',
        "p2p",
    )
    assert "msg_id" in msg

    polled = await broker.poll_messages(receiver["agent_id"])
    assert len(polled["messages"]) == 1
    assert (
        polled["messages"][0]["payload"]
        == '{"question": "What is the DB schema?"}'
    )

    # Poll auto-acknowledges, second poll returns empty
    repolled = await broker.poll_messages(receiver["agent_id"])
    assert len(repolled["messages"]) == 0


async def test_p2p_send_by_name(broker):
    """Send message using agent name instead of ID"""
    sender = await broker.register_agent("alice", [])
    receiver = await broker.register_agent("bob", [])

    msg = await broker.send_message(
        sender["agent_id"],
        "bob",
        '{"text": "hello"}',
        "p2p",
    )
    assert "msg_id" in msg

    polled = await broker.poll_messages(receiver["agent_id"])
    assert len(polled["messages"]) == 1


async def test_p2p_multiple_messages(broker):
    """Send multiple messages and poll them all"""
    s = await broker.register_agent("sender", [])
    r = await broker.register_agent("receiver", [])

    for i in range(5):
        await broker.send_message(
            s["agent_id"], r["agent_id"], f'{{"i": {i}}}', "p2p"
        )

    polled = await broker.poll_messages(r["agent_id"])
    assert len(polled["messages"]) == 5
