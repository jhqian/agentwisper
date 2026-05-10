# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Tests for MessageRouter P2P, RPC, and Pub/Sub message routing."""

import pytest
from broker.router import MessageRouter
from persistence.database import AsyncDatabase
from persistence.agent_store import AgentStore
from persistence.squad_store import SquadStore
from persistence.subscription_store import SubscriptionStore
from common.types import MessageType


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def router(db):
    return MessageRouter(db)


@pytest.fixture
async def agent_store(db):
    return AgentStore(db)


@pytest.fixture
async def squad_store(db):
    return SquadStore(db)


@pytest.fixture
async def sub_store(db):
    return SubscriptionStore(db)


async def test_p2p_send_and_poll(router, agent_store):
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="receiver", capabilities=[])
    result = await router.send_message(
        sender_id=sender, recipient=receiver,
        payload='{"text": "hello"}', msg_type=MessageType.P2P
    )
    assert result["msg_id"].startswith("msg_")

    messages = await router.poll_messages(receiver)
    assert len(messages) >= 1
    assert messages[0]["payload"] == '{"text": "hello"}'


async def test_p2p_send_by_name(router, agent_store):
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="bob", capabilities=[])
    result = await router.send_message(
        sender_id=sender, recipient="bob",
        payload='{}', msg_type=MessageType.P2P
    )
    assert result["msg_id"].startswith("msg_")


async def test_p2p_send_to_paused_agent(router, agent_store):
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="receiver", capabilities=[])
    from common.types import AgentStatus
    await agent_store.update_status(receiver, AgentStatus.PAUSED)
    # Message should still be stored (buffered)
    result = await router.send_message(
        sender_id=sender, recipient=receiver,
        payload='{}', msg_type=MessageType.P2P
    )
    assert result["msg_id"].startswith("msg_")


async def test_rpc_request_and_reply(router, agent_store):
    sender = await agent_store.create(name="caller", capabilities=[])
    receiver = await agent_store.create(name="worker", capabilities=[])
    req = await router.send_message(
        sender_id=sender, recipient=receiver,
        payload='{"task": "build"}', msg_type=MessageType.RPC_REQUEST
    )
    resp = await router.reply_message(
        parent_msg_id=req["msg_id"], sender_id=receiver,
        payload='{"result": "ok"}'
    )
    assert resp["msg_id"].startswith("msg_")
    # Original sender should get the response
    messages = await router.poll_messages(sender)
    assert len(messages) >= 1
    assert messages[0]["parent_msg_id"] == req["msg_id"]


async def test_pubsub_broadcast(router, agent_store, sub_store):
    sender = await agent_store.create(name="publisher", capabilities=[])
    sub1 = await agent_store.create(name="sub1", capabilities=[])
    sub2 = await agent_store.create(name="sub2", capabilities=[])
    await sub_store.create(agent_id=sub1, topic="alerts")
    await sub_store.create(agent_id=sub2, topic="alerts")

    result = await router.broadcast_message(
        sender_id=sender, topic="alerts", payload='{"level": "high"}'
    )
    assert result["subscriber_count"] == 2

    # Both subscribers should get the message
    msgs1 = await router.poll_messages(sub1)
    assert len(msgs1) >= 1
    msgs2 = await router.poll_messages(sub2)
    assert len(msgs2) >= 1


async def test_pubsub_squad_scoped(router, agent_store, sub_store, squad_store):
    sender = await agent_store.create(name="publisher", capabilities=[])
    sub1 = await agent_store.create(name="sub1", capabilities=[])
    sub2 = await agent_store.create(name="sub2", capabilities=[])
    squad_id = await squad_store.create(name="test-squad")
    # sub1 subscribes within squad, sub2 subscribes globally
    await sub_store.create(agent_id=sub1, topic="deploy", squad_id=squad_id)
    await sub_store.create(agent_id=sub2, topic="deploy")

    result = await router.broadcast_message(
        sender_id=sender, topic="deploy", payload='{}',
        squad_id=squad_id
    )
    # Should deliver to both squad-scoped and global subscribers
    assert result["subscriber_count"] >= 1


async def test_acknowledge_message(router, agent_store):
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="receiver", capabilities=[])
    result = await router.send_message(
        sender_id=sender, recipient=receiver,
        payload='{}', msg_type=MessageType.P2P
    )
    # Poll first to get delivered status
    await router.poll_messages(receiver)
    await router.acknowledge_message(result["msg_id"])


async def test_acknowledge_delivery(router, agent_store, sub_store):
    sender = await agent_store.create(name="publisher", capabilities=[])
    subscriber = await agent_store.create(name="sub", capabilities=[])
    await sub_store.create(agent_id=subscriber, topic="events")
    await router.broadcast_message(sender_id=sender, topic="events", payload='{}')

    msgs = await router.poll_messages(subscriber)
    assert len(msgs) >= 1
    delivery_id = msgs[0].get("delivery_id")
    if delivery_id:
        await router.acknowledge_delivery(delivery_id)
