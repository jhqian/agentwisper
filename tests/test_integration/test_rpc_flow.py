# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""End-to-end integration tests for RPC request/reply flow."""

import pytest

from broker.core import Broker
from common.config import BrokerConfig


@pytest.fixture
async def broker(tmp_path):
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    b = Broker(config)
    await b.start()
    yield b
    await b.stop()


async def test_rpc_full_flow(broker):
    """Request -> reply -> poll response"""
    caller = await broker.register_agent("caller", [])
    worker = await broker.register_agent("worker", [])

    req = await broker.send_message(
        caller["agent_id"],
        worker["agent_id"],
        '{"task": "compile", "target": "main"}',
        "rpc_request",
    )

    # Worker polls and gets request
    worker_msgs = await broker.poll_messages(worker["agent_id"])
    assert len(worker_msgs["messages"]) == 1
    assert worker_msgs["messages"][0]["msg_type"] == "rpc_request"

    # Worker replies
    resp = await broker.reply_message(
        req["msg_id"],
        worker["agent_id"],
        '{"result": "success", "binary": "build/main"}',
    )
    assert "msg_id" in resp

    # Caller polls and gets response
    caller_msgs = await broker.poll_messages(caller["agent_id"])
    assert len(caller_msgs["messages"]) == 1
    assert caller_msgs["messages"][0]["parent_msg_id"] == req["msg_id"]


async def test_rpc_correlation(broker):
    """Multiple RPC calls, verify correct correlation"""
    caller = await broker.register_agent("caller", [])
    worker = await broker.register_agent("worker", [])

    req1 = await broker.send_message(
        caller["agent_id"],
        worker["agent_id"],
        '{"task": "build"}',
        "rpc_request",
    )
    req2 = await broker.send_message(
        caller["agent_id"],
        worker["agent_id"],
        '{"task": "test"}',
        "rpc_request",
    )

    # Reply to second request only
    await broker.reply_message(
        req2["msg_id"], worker["agent_id"], '{"result": "tests pass"}'
    )

    # Caller gets reply for second request
    caller_msgs = await broker.poll_messages(caller["agent_id"])
    assert len(caller_msgs["messages"]) == 1
    assert caller_msgs["messages"][0]["parent_msg_id"] == req2["msg_id"]
