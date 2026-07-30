# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""End-to-end integration tests for RPC request/response flow using send."""

import pytest

from agentsquad.broker.core import Broker
from agentsquad.common.config import BrokerConfig


@pytest.fixture
async def broker(tmp_path):
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    b = Broker(config)
    await b.start()
    yield b
    await b.stop()


async def test_rpc_full_flow(broker):
    """Request -> send response -> poll response"""
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

    # Worker sends response back to caller
    resp = await broker.send_message(
        worker["agent_id"],
        caller["agent_id"],
        '{"result": "success", "binary": "build/main"}',
        "p2p",
    )
    assert "msg_id" in resp

    # Caller polls and gets response
    caller_msgs = await broker.poll_messages(caller["agent_id"])
    assert len(caller_msgs["messages"]) == 1


async def test_rpc_multiple_requests(broker):
    """Multiple RPC calls, worker responds to each via send"""
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

    # Worker polls both requests
    worker_msgs = await broker.poll_messages(worker["agent_id"])
    assert len(worker_msgs["messages"]) == 2

    # Worker sends response for second request only
    resp = await broker.send_message(
        worker["agent_id"],
        caller["agent_id"],
        '{"result": "tests pass"}',
        "p2p",
    )

    # Caller gets the response
    caller_msgs = await broker.poll_messages(caller["agent_id"])
    assert len(caller_msgs["messages"]) == 1
