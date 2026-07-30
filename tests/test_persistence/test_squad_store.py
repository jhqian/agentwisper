# Copyright 2026 agentsquad contributors
#
# Licensed under the Apache License, Version 2.0

import pytest
from agentsquad.persistence.squad_store import SquadStore
from agentsquad.persistence.agent_store import AgentStore
from agentsquad.common.types import SquadRole


@pytest.fixture
async def store(db):
    return SquadStore(db)


@pytest.fixture
async def agent_store(db):
    return AgentStore(db)


async def test_create_squad(store):
    squad_id = await store.create(name="dev-team", metadata={"project": "api"})
    assert squad_id.startswith("squad_")
    squad = await store.get(squad_id)
    assert squad["name"] == "dev-team"
    assert squad["status"] == "active"


async def test_list_active(store):
    await store.create(name="team-a")
    await store.create(name="team-b")
    active = await store.list_active()
    assert len(active) == 2


async def test_dissolve(store):
    squad_id = await store.create(name="temp")
    await store.dissolve(squad_id)
    squad = await store.get(squad_id)
    assert squad["status"] == "dissolved"
    assert squad["dissolved_at"] is not None


async def test_add_and_get_members(store, agent_store):
    squad_id = await store.create(name="team")
    a1 = await agent_store.create(name="agent1", capabilities=[])
    a2 = await agent_store.create(name="agent2", capabilities=[])
    await store.add_member(squad_id, a1, SquadRole.LEADER)
    await store.add_member(squad_id, a2, SquadRole.MEMBER)
    members = await store.get_members(squad_id)
    assert len(members) == 2


async def test_remove_member(store, agent_store):
    squad_id = await store.create(name="team")
    a1 = await agent_store.create(name="agent1", capabilities=[])
    await store.add_member(squad_id, a1, SquadRole.MEMBER)
    await store.remove_member(squad_id, a1)
    members = await store.get_members(squad_id)
    assert len(members) == 0


async def test_get_member_role(store, agent_store):
    squad_id = await store.create(name="team")
    a1 = await agent_store.create(name="agent1", capabilities=[])
    await store.add_member(squad_id, a1, SquadRole.LEADER)
    role = await store.get_member_role(squad_id, a1)
    assert role == "leader"


async def test_set_member_role(store, agent_store):
    squad_id = await store.create(name="team")
    a1 = await agent_store.create(name="agent1", capabilities=[])
    await store.add_member(squad_id, a1, SquadRole.MEMBER)
    await store.set_member_role(squad_id, a1, SquadRole.LEADER)
    role = await store.get_member_role(squad_id, a1)
    assert role == "leader"
