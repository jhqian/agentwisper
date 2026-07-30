# Copyright 2026 agentwisper contributors
#
# Licensed under the Apache License, Version 2.0

import pytest
from agentwisper.persistence.team_store import TeamStore
from agentwisper.persistence.agent_store import AgentStore


@pytest.fixture
async def store(db):
    return TeamStore(db)


@pytest.fixture
async def agent_store(db):
    return AgentStore(db)


async def test_create_team(store, agent_store):
    a1 = await agent_store.create(name="initiator", capabilities=[])
    a2 = await agent_store.create(name="member", capabilities=[])
    team_id = await store.create(initiator_id=a1, agent_ids=[a1, a2], topic="code-review")
    assert team_id.startswith("team_")
    team = await store.get(team_id)
    assert team["topic"] == "code-review"
    assert team["initiator_id"] == a1


async def test_get_members(store, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    team_id = await store.create(initiator_id=a1, agent_ids=[a1, a2])
    members = await store.get_members(team_id)
    assert len(members) == 2


async def test_list_active(store, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    await store.create(initiator_id=a1, agent_ids=[a1])
    active = await store.list_active()
    assert len(active) == 1


async def test_list_by_agent(store, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    await store.create(initiator_id=a1, agent_ids=[a1, a2])
    teams = await store.list_by_agent(a1)
    assert len(teams) == 1


async def test_dismiss(store, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    team_id = await store.create(initiator_id=a1, agent_ids=[a1])
    await store.dismiss(team_id)
    team = await store.get(team_id)
    assert team["status"] == "dismissed"


async def test_expire_expired_teams(store, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    # Create team with 1-second TTL and set expires_at in the past
    team_id = await store.create(initiator_id=a1, agent_ids=[a1], ttl_seconds=1)
    # Manually set expires_at to past to simulate expiry
    await store._db.execute(
        "UPDATE teams SET expires_at = '2020-01-01T00:00:00Z' WHERE team_id = ?",
        (team_id,)
    )
    count = await store.expire_expired_teams()
    assert count == 1
    team = await store.get(team_id)
    assert team["status"] == "expired"


async def test_team_with_ttl(store, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    team_id = await store.create(initiator_id=a1, agent_ids=[a1], ttl_seconds=3600)
    team = await store.get(team_id)
    assert team["ttl_seconds"] == 3600
    assert team["expires_at"] is not None
