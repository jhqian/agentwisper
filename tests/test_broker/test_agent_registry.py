# Licensed under the Apache License, Version 2.0

"""Tests for AgentRegistry business logic layer."""

import pytest
from broker.agent_registry import AgentRegistry
from persistence.database import AsyncDatabase


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
    result = await registry.register(name="test-agent", capabilities=["code"])
    assert result["agent_id"].startswith("agent_")
    assert result["assigned_name"] == "test-agent"
    info = await registry.get_info(result["agent_id"])
    assert info["name"] == "test-agent"
    assert info["status"] == "active"


async def test_deregister(registry):
    result = await registry.register(name="test", capabilities=[])
    await registry.deregister(result["agent_id"])
    info = await registry.get_info(result["agent_id"])
    assert info is not None
    assert info["status"] == "disconnected"


async def test_deregister_nonexistent(registry):
    with pytest.raises(ValueError, match="not found"):
        await registry.deregister("agent_nonexistent")


async def test_resolve_by_id(registry):
    result = await registry.register(name="test", capabilities=[])
    resolved = await registry.resolve_recipient(result["agent_id"])
    assert resolved == result["agent_id"]


async def test_resolve_by_name(registry):
    result = await registry.register(name="unique-name", capabilities=[])
    resolved = await registry.resolve_recipient("unique-name")
    assert resolved == result["agent_id"]


async def test_resolve_nonexistent(registry):
    resolved = await registry.resolve_recipient("nonexistent")
    assert resolved is None


async def test_resolve_disconnected_by_id_returns_none(registry):
    result = await registry.register(name="test", capabilities=[])
    await registry.deregister(result["agent_id"])
    resolved = await registry.resolve_recipient(result["agent_id"])
    assert resolved is None


async def test_resolve_disconnected_by_name_returns_none(registry):
    result = await registry.register(name="test", capabilities=[])
    await registry.deregister(result["agent_id"])
    resolved = await registry.resolve_recipient("test")
    assert resolved is None


async def test_list_agents(registry):
    await registry.register(name="a1", capabilities=[])
    await registry.register(name="a2", capabilities=[])
    agents = await registry.list_agents()
    assert len(agents) == 2


# ---------------------------------------------------------------------------
# Unique name tests
# ---------------------------------------------------------------------------


async def test_register_unique_name_no_collision(registry):
    """First registration gets the exact requested name."""
    result = await registry.register(name="dev", capabilities=[])
    assert result["assigned_name"] == "dev"


async def test_register_duplicate_name_gets_suffix(registry):
    """Second registration with same name gets -1 suffix."""
    r1 = await registry.register(name="dev", capabilities=[])
    r2 = await registry.register(name="dev", capabilities=[])
    assert r1["assigned_name"] == "dev"
    assert r2["assigned_name"] == "dev-1"


async def test_register_increment_suffix(registry):
    """Suffixes increment: dev, dev-1, dev-2."""
    await registry.register(name="dev", capabilities=[])
    await registry.register(name="dev", capabilities=[])
    r3 = await registry.register(name="dev", capabilities=[])
    assert r3["assigned_name"] == "dev-2"


async def test_register_independent_bases(registry):
    """Different base names don't interfere."""
    r1 = await registry.register(name="dev", capabilities=[])
    r2 = await registry.register(name="test", capabilities=[])
    assert r1["assigned_name"] == "dev"
    assert r2["assigned_name"] == "test"


async def test_register_reclaim_after_deregister(registry):
    """After deregister, name is released — new reg gets the same name."""
    r1 = await registry.register(name="dev", capabilities=[])
    await registry.deregister(r1["agent_id"])
    r2 = await registry.register(name="dev", capabilities=[])
    assert r2["assigned_name"] == "dev"


# ---------------------------------------------------------------------------
# Soft-delete and reconnect tests
# ---------------------------------------------------------------------------


async def test_deregister_preserves_squad_membership(registry, db):
    result = await registry.register(name="test", capabilities=[])
    agent_id = result["agent_id"]
    await db.execute(
        "INSERT INTO squads (squad_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        ("squad_test", "test-squad", "active", "2026-01-01T00:00:00Z"),
    )
    await db.execute(
        "INSERT INTO squad_memberships (squad_id, agent_id, joined_at, role) VALUES (?, ?, ?, ?)",
        ("squad_test", agent_id, "2026-01-01T00:00:00Z", "member"),
    )
    await registry.deregister(agent_id)
    rows = await db.execute_fetchall(
        "SELECT * FROM squad_memberships WHERE agent_id = ?", (agent_id,)
    )
    assert len(rows) == 1


async def test_deregister_preserves_subscriptions(registry, db):
    result = await registry.register(name="test", capabilities=[])
    agent_id = result["agent_id"]
    await db.execute(
        "INSERT INTO subscriptions (sub_id, agent_id, topic, created_at) VALUES (?, ?, ?, ?)",
        ("sub_test", agent_id, "alerts", "2026-01-01T00:00:00Z"),
    )
    await registry.deregister(agent_id)
    rows = await db.execute_fetchall(
        "SELECT * FROM subscriptions WHERE agent_id = ?", (agent_id,)
    )
    assert len(rows) == 1


async def test_reconnect_restores_disconnected_agent(registry):
    r = await registry.register(name="dev", capabilities=["code"], session_name="sess_old")
    agent_id = r["agent_id"]
    await registry.deregister(agent_id)
    result = await registry.reconnect(name="dev", session_name="sess_new")
    assert result["agent_id"] == agent_id
    assert result["status"] == "active"
    info = await registry.get_info(agent_id)
    assert info["status"] == "active"
    assert info["session_name"] == "sess_new"


async def test_reconnect_nonexistent_raises(registry):
    with pytest.raises(ValueError, match="never been registered or may have expired"):
        await registry.reconnect(name="nonexistent", session_name="sess_1")


async def test_reconnect_active_agent_raises(registry):
    await registry.register(name="dev", capabilities=[])
    with pytest.raises(ValueError, match="status 'active'"):
        await registry.reconnect(name="dev", session_name="sess_1")


async def test_reconnect_preserves_capabilities(registry):
    r = await registry.register(name="dev", capabilities=["code", "review"])
    agent_id = r["agent_id"]
    await registry.deregister(agent_id)
    result = await registry.reconnect(name="dev", session_name="sess_2")
    assert result["agent_id"] == agent_id
    info = await registry.get_info(agent_id)
    assert info["capabilities"] == '["code", "review"]'


async def test_reconnect_active_agent_error_mentions_status(registry):
    await registry.register(name="dev", capabilities=[])
    with pytest.raises(ValueError, match="status 'active'"):
        await registry.reconnect(name="dev")


async def test_reconnect_never_registered_error_suggests_cause(registry):
    with pytest.raises(ValueError, match="never been registered or may have expired"):
        await registry.reconnect(name="ghost")


async def test_reconnect_preserves_squad(registry, db):
    r = await registry.register(name="dev", capabilities=[])
    agent_id = r["agent_id"]
    await db.execute(
        "INSERT INTO squads (squad_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        ("squad_test", "test-squad", "active", "2026-01-01T00:00:00Z"),
    )
    await db.execute(
        "INSERT INTO squad_memberships (squad_id, agent_id, joined_at, role) VALUES (?, ?, ?, ?)",
        ("squad_test", agent_id, "2026-01-01T00:00:00Z", "member"),
    )
    await registry.deregister(agent_id)
    result = await registry.reconnect(name="dev", session_name="sess_3")
    assert result["agent_id"] == agent_id
    rows = await db.execute_fetchall(
        "SELECT * FROM squad_memberships WHERE agent_id = ?", (agent_id,)
    )
    assert len(rows) == 1
