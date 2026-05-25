# Copyright 2026 agentsquad contributors
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


async def test_update_status_disconnected(store):
    agent_id = await store.create(name="test", capabilities=[])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    agent = await store.get(agent_id)
    assert agent["status"] == "disconnected"


async def test_create_with_session_name(store):
    agent_id = await store.create(name="dev", capabilities=["code"], session_name="sess_abc")
    agent = await store.get(agent_id)
    assert agent["session_name"] == "sess_abc"


async def test_create_without_session_name(store):
    agent_id = await store.create(name="dev", capabilities=["code"])
    agent = await store.get(agent_id)
    assert agent["session_name"] is None


async def test_update_session_name(store):
    agent_id = await store.create(name="dev", capabilities=["code"])
    await store.update_session_name(agent_id, "sess_new")
    agent = await store.get(agent_id)
    assert agent["session_name"] == "sess_new"


async def test_get_disconnected_by_name(store):
    agent_id = await store.create(name="dev", capabilities=["code"])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    result = await store.get_disconnected_by_name("dev")
    assert result is not None
    assert result["agent_id"] == agent_id
    assert result["status"] == "disconnected"


async def test_get_disconnected_by_name_not_found_when_active(store):
    await store.create(name="dev", capabilities=["code"])
    result = await store.get_disconnected_by_name("dev")
    assert result is None


async def test_get_disconnected_by_name_nonexistent(store):
    result = await store.get_disconnected_by_name("nonexistent")
    assert result is None


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


async def test_find_names_by_prefix_exact(store):
    await store.create(name="dev", capabilities=[])
    names = await store.find_names_by_prefix("dev")
    assert names == ["dev"]


async def test_find_names_by_prefix_with_suffixes(store):
    await store.create(name="dev", capabilities=[])
    await store.create(name="dev-1", capabilities=[])
    await store.create(name="dev-2", capabilities=[])
    names = await store.find_names_by_prefix("dev")
    assert sorted(names) == ["dev", "dev-1", "dev-2"]


async def test_find_names_by_prefix_no_match(store):
    await store.create(name="test", capabilities=[])
    names = await store.find_names_by_prefix("dev")
    assert names == []


async def test_find_names_by_prefix_does_not_overmatch(store):
    """LIKE 'dev-%' matches 'dev-team' but that name is returned too."""
    await store.create(name="dev", capabilities=[])
    await store.create(name="dev-team", capabilities=[])
    names = await store.find_names_by_prefix("dev")
    assert sorted(names) == ["dev", "dev-team"]


async def test_find_names_includes_disconnected(store):
    agent_id = await store.create(name="dev", capabilities=[])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    names = await store.find_names_by_prefix("dev")
    assert names == ["dev"]


async def test_update_status_sets_disconnected_at(store):
    agent_id = await store.create(name="test", capabilities=["code"])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    agent = await store.get(agent_id)
    assert agent["disconnected_at"] is not None


async def test_update_status_clears_disconnected_at_on_reconnect(store):
    agent_id = await store.create(name="test", capabilities=["code"])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    await store.update_status(agent_id, AgentStatus.ACTIVE)
    agent = await store.get(agent_id)
    assert agent["disconnected_at"] is None


async def test_cleanup_expired_agents_removes_old(store, db):
    agent_id = await store.create(name="old-agent", capabilities=["code"])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    from datetime import datetime, timezone, timedelta
    old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    await db.execute(
        "UPDATE agents SET disconnected_at = ? WHERE agent_id = ?",
        (old_time, agent_id),
    )
    removed = await store.cleanup_expired_agents(ttl_days=7)
    assert removed == 1
    assert await store.get(agent_id) is None


async def test_cleanup_preserves_recent_disconnected(store):
    agent_id = await store.create(name="recent-agent", capabilities=["code"])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    removed = await store.cleanup_expired_agents(ttl_days=7)
    assert removed == 0
    assert await store.get(agent_id) is not None


async def test_cleanup_cascades_to_messages(store, db):
    from datetime import datetime, timezone, timedelta
    agent_id = await store.create(name="old-agent", capabilities=["code"])
    await store.update_status(agent_id, AgentStatus.DISCONNECTED)
    old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    await db.execute(
        "UPDATE agents SET disconnected_at = ? WHERE agent_id = ?",
        (old_time, agent_id),
    )
    await db.execute(
        "INSERT INTO messages (msg_id, sender_id, recipient_id, msg_type, payload, status, created_at) "
        "VALUES (?, 'system', ?, 'notification', 'test', 'pending', ?)",
        ("msg_1", agent_id, old_time),
    )
    removed = await store.cleanup_expired_agents(ttl_days=7)
    assert removed == 1
    msgs = await db.execute_fetchall("SELECT * FROM messages WHERE recipient_id = ?", (agent_id,))
    assert len(msgs) == 0
