# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Tests for MessageStore CRUD, delivery log fan-out, and query capabilities."""

import pytest
from persistence.message_store import MessageStore
from persistence.agent_store import AgentStore
from common.types import MessageType, MessageStatus


@pytest.fixture
async def store(db):
    return MessageStore(db)

@pytest.fixture
async def agents(db):
    agent_store = AgentStore(db)
    a1 = await agent_store.create(name="sender", capabilities=[])
    a2 = await agent_store.create(name="receiver", capabilities=[])
    return a1, a2


async def test_create_p2p_message(store, agents):
    sender, receiver = agents
    msg_id = await store.create(
        sender_id=sender,
        recipient_id=receiver,
        msg_type=MessageType.P2P,
        payload='{"text": "hello"}',
    )
    assert msg_id.startswith("msg_")


async def test_get_pending_for_agent(store, agents):
    sender, receiver = agents
    await store.create(sender_id=sender, recipient_id=receiver,
                       msg_type=MessageType.P2P, payload='{}')
    messages = await store.get_pending_for_agent(receiver)
    assert len(messages) == 1
    assert messages[0]["recipient_id"] == receiver
    assert messages[0]["status"] == "pending"


async def test_mark_delivered(store, agents):
    sender, receiver = agents
    msg_id = await store.create(sender_id=sender, recipient_id=receiver,
                                msg_type=MessageType.P2P, payload='{}')
    await store.mark_delivered(msg_id)
    messages = await store.get_pending_for_agent(receiver)
    assert len(messages) == 0


async def test_mark_acknowledged(store, agents):
    sender, receiver = agents
    msg_id = await store.create(sender_id=sender, recipient_id=receiver,
                                msg_type=MessageType.P2P, payload='{}')
    await store.mark_delivered(msg_id)
    await store.mark_acknowledged(msg_id)
    msg = await store.get(msg_id)
    assert msg["status"] == "acknowledged"


async def test_rpc_request_and_reply(store, agents):
    sender, receiver = agents
    req_id = await store.create(sender_id=sender, recipient_id=receiver,
                                msg_type=MessageType.RPC_REQUEST, payload='{"task": "build"}')
    resp_id = await store.create(sender_id=receiver, recipient_id=sender,
                                 msg_type=MessageType.RPC_RESPONSE,
                                 payload='{"result": "ok"}',
                                 parent_msg_id=req_id)
    msg = await store.get(resp_id)
    assert msg["parent_msg_id"] == req_id
    assert msg["msg_type"] == "rpc_response"


async def test_create_delivery_logs(store, agents):
    sender, _ = agents
    msg_id = await store.create(sender_id=sender, recipient_id=None,
                                msg_type=MessageType.PUBSUB, payload='{}',
                                topic="alerts")
    recipient_ids = ["r1", "r2"]
    await store.create_delivery_logs(msg_id, recipient_ids)
    logs = await store.get_pending_deliveries("r1")
    assert len(logs) == 1
    assert logs[0]["msg_id"] == msg_id


async def test_mark_delivery_acknowledged(store, agents):
    sender, _ = agents
    msg_id = await store.create(sender_id=sender, recipient_id=None,
                                msg_type=MessageType.PUBSUB, payload='{}',
                                topic="alerts")
    await store.create_delivery_logs(msg_id, ["r1"])
    logs = await store.get_pending_deliveries("r1")
    await store.mark_delivery_delivered(logs[0]["delivery_id"])
    await store.mark_delivery_acknowledged(logs[0]["delivery_id"])
    updated = await store.get_pending_deliveries("r1")
    assert len(updated) == 0


async def test_query_messages(store, agents):
    sender, receiver = agents
    await store.create(sender_id=sender, recipient_id=receiver,
                       msg_type=MessageType.P2P, payload='{"a": 1}')
    await store.create(sender_id=sender, recipient_id=receiver,
                       msg_type=MessageType.P2P, payload='{"a": 2}')
    results = await store.query(sender_id=sender, limit=10)
    assert len(results) == 2


async def test_query_by_time_range(store, agents):
    sender, receiver = agents
    await store.create(sender_id=sender, recipient_id=receiver,
                       msg_type=MessageType.P2P, payload='{}')
    results = await store.query(
        sender_id=sender,
        time_start="2020-01-01T00:00:00Z",
        time_end="2030-12-31T23:59:59Z",
        limit=10,
    )
    assert len(results) == 1
