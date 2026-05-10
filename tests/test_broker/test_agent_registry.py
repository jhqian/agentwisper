# Licensed under the Apache License, Version 2.0

"""Tests for AgentRegistry business logic layer."""

import pytest
from broker.agent_registry import AgentRegistry
from persistence.database import AsyncDatabase
from persistence.agent_store import AgentStore
from persistence.message_store import MessageStore
from common.types import AgentStatus, MessageType


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def registry(db):
    return AgentRegistry(db)


async def test_register(registry):
    agent_id = await registry.register(name="test-agent", capabilities=["code"])
    assert agent_id.startswith("agent_")
    info = await registry.get_info(agent_id)
    assert info["name"] == "test-agent"
    assert info["status"] == "active"


async def test_deregister(registry):
    agent_id = await registry.register(name="test", capabilities=[])
    await registry.deregister(agent_id)
    info = await registry.get_info(agent_id)
    assert info is None


async def test_deregister_nonexistent(registry):
    with pytest.raises(ValueError, match="not found"):
        await registry.deregister("agent_nonexistent")


async def test_pause_and_resume(registry):
    agent_id = await registry.register(name="test", capabilities=[])
    await registry.pause(agent_id)
    info = await registry.get_info(agent_id)
    assert info["status"] == "paused"

    result = await registry.resume(agent_id)
    assert result["status"] == "active"
    info = await registry.get_info(agent_id)
    assert info["status"] == "active"


async def test_resume_returns_buffered_count(registry, db):
    agent_id = await registry.register(name="test", capabilities=[])
    await registry.pause(agent_id)
    # Send a message to the paused agent
    msg_store = MessageStore(db)
    sender = await AgentStore(db).create(name="sender", capabilities=[])
    await msg_store.create(
        sender_id=sender,
        recipient_id=agent_id,
        msg_type=MessageType.P2P,
        payload="{}",
    )
    result = await registry.resume(agent_id)
    assert result["buffered_count"] == 1


async def test_pause_non_active_fails(registry):
    agent_id = await registry.register(name="test", capabilities=[])
    await registry.pause(agent_id)
    with pytest.raises(ValueError, match="Cannot pause"):
        await registry.pause(agent_id)


async def test_resume_non_paused_fails(registry):
    agent_id = await registry.register(name="test", capabilities=[])
    with pytest.raises(ValueError, match="Cannot resume"):
        await registry.resume(agent_id)


async def test_disconnect_and_reconnect(registry):
    agent_id = await registry.register(name="test", capabilities=[])
    await registry.disconnect(agent_id)
    info = await registry.get_info(agent_id)
    assert info["status"] == "disconnected"

    await registry.reconnect(agent_id)
    info = await registry.get_info(agent_id)
    assert info["status"] == "active"


async def test_resolve_by_id(registry):
    agent_id = await registry.register(name="test", capabilities=[])
    resolved = await registry.resolve_recipient(agent_id)
    assert resolved == agent_id


async def test_resolve_by_name(registry):
    agent_id = await registry.register(name="unique-name", capabilities=[])
    resolved = await registry.resolve_recipient("unique-name")
    assert resolved == agent_id


async def test_resolve_nonexistent(registry):
    resolved = await registry.resolve_recipient("nonexistent")
    assert resolved is None


async def test_heartbeat(registry):
    agent_id = await registry.register(name="test", capabilities=[])
    await registry.heartbeat(agent_id)
    info = await registry.get_info(agent_id)
    assert info["last_heartbeat"] is not None


async def test_list_agents(registry):
    await registry.register(name="a1", capabilities=[])
    await registry.register(name="a2", capabilities=[])
    agents = await registry.list_agents()
    assert len(agents) == 2
