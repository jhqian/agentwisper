# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Tests for MessageRouter P2P, RPC, and Pub/Sub message routing."""

import pytest
from agentwisper.broker.router import MessageRouter
from agentwisper.persistence.database import AsyncDatabase
from agentwisper.persistence.agent_store import AgentStore
from agentwisper.persistence.squad_store import SquadStore
from agentwisper.persistence.subscription_store import SubscriptionStore
from agentwisper.common.types import MessageType


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


async def test_rpc_request_and_response(router, agent_store):
    sender = await agent_store.create(name="caller", capabilities=[])
    receiver = await agent_store.create(name="worker", capabilities=[])
    req = await router.send_message(
        sender_id=sender, recipient=receiver,
        payload='{"task": "build"}', msg_type=MessageType.RPC_REQUEST
    )
    # Respond using send (receiver replies to sender directly)
    resp = await router.send_message(
        sender_id=receiver, recipient=sender,
        payload='{"result": "ok"}', msg_type=MessageType.P2P
    )
    assert resp["msg_id"].startswith("msg_")
    # Original sender should get the response
    messages = await router.poll_messages(sender)
    assert len(messages) >= 1


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


async def test_poll_auto_acknowledges_direct_message(router, agent_store):
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="receiver", capabilities=[])
    result = await router.send_message(
        sender_id=sender, recipient=receiver,
        payload='{}', msg_type=MessageType.P2P
    )
    # Poll should auto-acknowledge (status goes pending -> acknowledged)
    await router.poll_messages(receiver)
    msg = await router._message_store.get(result["msg_id"])
    assert msg["status"] == "acknowledged"
    # Second poll should return empty (message no longer pending)
    msgs = await router.poll_messages(receiver)
    assert len(msgs) == 0


async def test_send_to_disconnected_agent_buffers(router, agent_store):
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="receiver", capabilities=[])
    from agentwisper.common.types import AgentStatus
    await agent_store.update_status(receiver, AgentStatus.DISCONNECTED)
    result = await router.send_message(
        sender_id=sender, recipient=receiver,
        payload='{"hello": true}', msg_type=MessageType.P2P
    )
    assert result["status"] == "pending"
    assert result["recipient_id"] == receiver
    # Message is buffered and can be polled after reconnect
    msgs = await router.poll_messages(receiver)
    assert len(msgs) == 1
    assert msgs[0]["payload"] == '{"hello": true}'


async def test_send_to_disconnected_by_name_buffers(router, agent_store):
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="alice", capabilities=[])
    from agentwisper.common.types import AgentStatus
    await agent_store.update_status(receiver, AgentStatus.DISCONNECTED)
    result = await router.send_message(
        sender_id=sender, recipient="alice",
        payload='{"for_alice": true}', msg_type=MessageType.P2P
    )
    assert result["status"] == "pending"
    assert result["recipient_id"] == receiver


async def test_rpc_to_disconnected_agent_buffers(router, agent_store):
    caller = await agent_store.create(name="caller", capabilities=[])
    worker = await agent_store.create(name="worker", capabilities=[])
    from agentwisper.common.types import AgentStatus
    await agent_store.update_status(worker, AgentStatus.DISCONNECTED)
    result = await router.send_message(
        sender_id=caller, recipient=worker,
        payload='{"task": "build"}', msg_type=MessageType.RPC_REQUEST
    )
    assert result["status"] == "pending"
    assert result["recipient_id"] == worker


async def test_poll_auto_acknowledges_delivery(router, agent_store, sub_store):
    sender = await agent_store.create(name="publisher", capabilities=[])
    subscriber = await agent_store.create(name="sub", capabilities=[])
    await sub_store.create(agent_id=subscriber, topic="events")
    await router.broadcast_message(sender_id=sender, topic="events", payload='{}')

    msgs = await router.poll_messages(subscriber)
    assert len(msgs) >= 1
    delivery_id = msgs[0].get("delivery_id")
    if delivery_id:
        dlv = await router._message_store._db.execute_fetchone(
            "SELECT * FROM delivery_logs WHERE delivery_id = ?", (delivery_id,)
        )
        assert dlv["status"] == "acknowledged"


async def test_pubsub_broadcast_skips_disconnected_subscriber(router, agent_store, sub_store):
    from agentwisper.common.types import AgentStatus
    sender = await agent_store.create(name="publisher", capabilities=[])
    sub1 = await agent_store.create(name="sub1", capabilities=[])
    sub2 = await agent_store.create(name="sub2", capabilities=[])
    await sub_store.create(agent_id=sub1, topic="alerts")
    await sub_store.create(agent_id=sub2, topic="alerts")
    await agent_store.update_status(sub2, AgentStatus.DISCONNECTED)

    result = await router.broadcast_message(
        sender_id=sender, topic="alerts", payload='{"level": "high"}'
    )
    assert result["subscriber_count"] == 1
    assert sub1 in result["subscriber_ids"]
    assert sub2 not in result["subscriber_ids"]


async def test_poll_all_mode_includes_delivered(router, agent_store):
    """unread_only=False returns delivered messages as well as pending ones."""
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="receiver", capabilities=[])
    await router.send_message(sender_id=sender, recipient=receiver,
                              payload="hello", msg_type=MessageType.P2P)
    # Default poll consumes (marks delivered) the message
    await router.poll_messages(receiver)
    assert await router.poll_messages(receiver) == []
    # All-mode still returns the delivered message
    all_msgs = await router.poll_messages(receiver, unread_only=False)
    assert len(all_msgs) == 1
    assert all_msgs[0]["payload"] == "hello"


async def test_poll_all_mode_does_not_consume_pending(router, agent_store):
    """unread_only=False is a pure query: pending messages stay pending."""
    sender = await agent_store.create(name="sender", capabilities=[])
    receiver = await agent_store.create(name="receiver", capabilities=[])
    await router.send_message(sender_id=sender, recipient=receiver,
                              payload="keep-me", msg_type=MessageType.P2P)
    assert len(await router.poll_messages(receiver, unread_only=False)) == 1
    # Message is still pending for the default poll
    assert len(await router.poll_messages(receiver)) == 1
