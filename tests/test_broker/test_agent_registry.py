# Licensed under the Apache License, Version 2.0

"""Tests for AgentRegistry business logic layer."""

import pytest
from agentwisper.broker.agent_registry import AgentRegistry
from agentwisper.persistence.database import AsyncDatabase


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
    result = await registry.register(name="test-agent")
    assert result["agent_id"].startswith("agent_")
    assert result["assigned_name"] == "test-agent"
    info = await registry.get_info(result["agent_id"])
    assert info["name"] == "test-agent"
    assert info["status"] == "active"


async def test_deregister(registry):
    result = await registry.register(name="test")
    await registry.deregister(result["agent_id"])
    info = await registry.get_info(result["agent_id"])
    assert info is not None
    assert info["status"] == "disconnected"


async def test_deregister_nonexistent(registry):
    with pytest.raises(ValueError, match="not found"):
        await registry.deregister("agent_nonexistent")


async def test_resolve_by_id(registry):
    result = await registry.register(name="test")
    resolved = await registry.resolve_recipient(result["agent_id"])
    assert resolved == result["agent_id"]


async def test_resolve_by_name(registry):
    result = await registry.register(name="unique-name")
    resolved = await registry.resolve_recipient("unique-name")
    assert resolved == result["agent_id"]


async def test_resolve_nonexistent(registry):
    resolved = await registry.resolve_recipient("nonexistent")
    assert resolved is None


async def test_resolve_disconnected_by_id_returns_id(registry):
    result = await registry.register(name="test")
    await registry.deregister(result["agent_id"])
    resolved = await registry.resolve_recipient(result["agent_id"])
    assert resolved == result["agent_id"]


async def test_resolve_disconnected_by_name_returns_id(registry):
    result = await registry.register(name="test")
    await registry.deregister(result["agent_id"])
    resolved = await registry.resolve_recipient("test")
    assert resolved == result["agent_id"]


async def test_list_agents(registry):
    await registry.register(name="a1")
    await registry.register(name="a2")
    agents = await registry.list_agents()
    assert len(agents) == 2


# ---------------------------------------------------------------------------
# Unique name tests
# ---------------------------------------------------------------------------


async def test_register_unique_name_no_collision(registry):
    """First registration gets the exact requested name."""
    result = await registry.register(name="dev")
    assert result["assigned_name"] == "dev"


async def test_register_duplicate_name_raises(registry):
    """Second registration with same name raises ValueError."""
    r1 = await registry.register(name="dev")
    with pytest.raises(ValueError, match="already registered"):
        await registry.register(name="dev")


async def test_register_duplicate_name_force_allows(registry):
    """Force=True allows duplicate name registration."""
    r1 = await registry.register(name="dev")
    r2 = await registry.register(name="dev", force=True)
    assert r1["assigned_name"] == "dev"
    assert r2["assigned_name"] == "dev"
    assert r1["agent_id"] != r2["agent_id"]


async def test_register_independent_bases(registry):
    """Different base names don't interfere."""
    r1 = await registry.register(name="dev")
    r2 = await registry.register(name="test")
    assert r1["assigned_name"] == "dev"
    assert r2["assigned_name"] == "test"


async def test_register_reclaim_after_deregister_requires_force(registry):
    """After deregister, name is NOT released (soft delete). Must use force."""
    r1 = await registry.register(name="dev")
    await registry.deregister(r1["agent_id"])
    with pytest.raises(ValueError, match="already registered"):
        await registry.register(name="dev")
    r2 = await registry.register(name="dev", force=True)
    assert r2["assigned_name"] == "dev"


# ---------------------------------------------------------------------------
# Soft-delete and reconnect tests
# ---------------------------------------------------------------------------


async def test_deregister_preserves_squad_membership(registry, db):
    result = await registry.register(name="test")
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
    result = await registry.register(name="test")
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
    r = await registry.register(name="dev", session_name="sess_old")
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


async def test_reconnect_active_agent_succeeds(registry):
    r = await registry.register(name="dev")
    agent_id = r["agent_id"]
    result = await registry.reconnect(name="dev", session_name="sess_new")
    assert result["agent_id"] == agent_id
    assert result["status"] == "active"
    info = await registry.get_info(agent_id)
    assert info["session_name"] == "sess_new"


async def test_reconnect_active_agent_no_error(registry):
    r = await registry.register(name="dev")
    agent_id = r["agent_id"]
    result = await registry.reconnect(name="dev")
    assert result["agent_id"] == agent_id
    assert result["status"] == "active"


async def test_reconnect_never_registered_error_suggests_cause(registry):
    with pytest.raises(ValueError, match="never been registered or may have expired"):
        await registry.reconnect(name="ghost")


async def test_reconnect_preserves_squad(registry, db):
    r = await registry.register(name="dev")
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


# ---------------------------------------------------------------------------
# Credential-based reconnect tests
# ---------------------------------------------------------------------------


async def test_reconnect_with_credentials(registry):
    r = await registry.register(name="dev", session_name="sess_old")
    agent_id = r["agent_id"]
    await registry.deregister(agent_id)
    result = await registry.reconnect(
        name="dev", agent_id=agent_id, session_name="sess_new"
    )
    assert result["agent_id"] == agent_id
    assert result["status"] == "active"
    info = await registry.get_info(agent_id)
    assert info["session_name"] == "sess_new"


async def test_reconnect_wrong_agent_id(registry):
    r = await registry.register(name="dev")
    await registry.deregister(r["agent_id"])
    with pytest.raises(ValueError, match="not found"):
        await registry.reconnect(
            name="dev", agent_id="agent_wrong_id", session_name="sess_new"
        )


async def test_reconnect_wrong_name(registry):
    r = await registry.register(name="dev")
    agent_id = r["agent_id"]
    await registry.deregister(agent_id)
    with pytest.raises(ValueError, match="Credential mismatch"):
        await registry.reconnect(
            name="wrong-name", agent_id=agent_id, session_name="sess_new"
        )


async def test_reconnect_nonexistent_agent_id(registry):
    with pytest.raises(ValueError, match="not found"):
        await registry.reconnect(
            name="dev", agent_id="agent_nonexistent", session_name="sess_new"
        )


async def test_reconnect_active_agent_with_credentials(registry):
    r = await registry.register(name="dev", session_name="old")
    result = await registry.reconnect(
        name="dev", agent_id=r["agent_id"], session_name="new"
    )
    assert result["agent_id"] == r["agent_id"]
    assert result["status"] == "active"
    info = await registry.get_info(r["agent_id"])
    assert info["session_name"] == "new"


async def test_registry_list_active_excludes_disconnected(registry):
    a1 = await registry.register(name="alive")
    a2 = await registry.register(name="ghost")
    await registry.deregister(a2["agent_id"])
    agents = await registry.list_active()
    ids = [a["agent_id"] for a in agents]
    assert a1["agent_id"] in ids
    assert a2["agent_id"] not in ids


async def test_registry_list_active_delegates_to_store(registry):
    await registry.register(name="dev")
    agents = await registry.list_active()
    assert len(agents) == 1
    assert agents[0]["name"] == "dev"
