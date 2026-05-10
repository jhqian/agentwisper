# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Tests for AgentStore CRUD and lifecycle operations."""

import pytest
from persistence.agent_store import AgentStore
from common.types import AgentStatus


@pytest.fixture
async def store(db):
    return AgentStore(db)


async def test_create_agent(store):
    agent_id = await store.create(
        name="test-agent",
        capabilities=["code"],
        metadata={"env": "dev"},
    )
    assert agent_id.startswith("agent_")


async def test_get_agent(store):
    agent_id = await store.create(name="test-agent", capabilities=[])
    agent = await store.get(agent_id)
    assert agent is not None
    assert agent["name"] == "test-agent"
    assert agent["status"] == "active"


async def test_get_agent_by_name(store):
    await store.create(name="unique-name", capabilities=[])
    agent = await store.get_by_name("unique-name")
    assert agent is not None
    assert agent["name"] == "unique-name"


async def test_get_nonexistent_agent(store):
    agent = await store.get("agent_nonexistent")
    assert agent is None


async def test_update_status(store):
    agent_id = await store.create(name="test", capabilities=[])
    await store.update_status(agent_id, AgentStatus.PAUSED)
    agent = await store.get(agent_id)
    assert agent["status"] == "paused"


async def test_update_heartbeat(store):
    agent_id = await store.create(name="test", capabilities=[])
    await store.update_heartbeat(agent_id, "2026-05-09T10:00:30Z")
    agent = await store.get(agent_id)
    assert agent["last_heartbeat"] == "2026-05-09T10:00:30Z"


async def test_set_squad(store):
    agent_id = await store.create(name="test", capabilities=[])
    await store.set_squad(agent_id, "squad_123")
    agent = await store.get(agent_id)
    assert agent["squad_id"] == "squad_123"


async def test_clear_squad(store):
    agent_id = await store.create(name="test", capabilities=[])
    await store.set_squad(agent_id, "squad_123")
    await store.set_squad(agent_id, None)
    agent = await store.get(agent_id)
    assert agent["squad_id"] is None


async def test_set_team(store):
    agent_id = await store.create(name="test", capabilities=[])
    await store.set_team(agent_id, "team_123")
    agent = await store.get(agent_id)
    assert agent["current_team_id"] == "team_123"


async def test_delete_agent(store):
    agent_id = await store.create(name="test", capabilities=[])
    await store.delete(agent_id)
    agent = await store.get(agent_id)
    assert agent is None


async def test_list_agents(store):
    await store.create(name="agent-a", capabilities=[])
    await store.create(name="agent-b", capabilities=[])
    agents = await store.list_all()
    assert len(agents) == 2


async def test_list_agents_by_squad(store):
    a1 = await store.create(name="a1", capabilities=[])
    a2 = await store.create(name="a2", capabilities=[])
    await store.set_squad(a1, "squad_x")
    await store.set_squad(a2, "squad_y")
    agents = await store.list_by_squad("squad_x")
    assert len(agents) == 1
    assert agents[0]["agent_id"] == a1
