# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Tests for SquadManager business logic with role-based permissions."""

import pytest

from agentwisper.broker.squad_manager import SquadManager
from agentwisper.common.types import SquadRole
from agentwisper.persistence.agent_store import AgentStore
from agentwisper.persistence.database import AsyncDatabase


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def manager(db):
    return SquadManager(db)


@pytest.fixture
async def agent_store(db):
    return AgentStore(db)


async def test_create_squad(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    squad_id = await manager.create(name="dev-team", creator_agent_id=leader_id)
    assert squad_id.startswith("squad_")
    info = await manager.get_info(squad_id)
    assert info["squad"]["name"] == "dev-team"
    assert info["squad"]["status"] == "active"
    # Creator should be leader
    role = await manager._squad_store.get_member_role(squad_id, leader_id)
    assert role == "leader"


async def test_join_squad(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    members = await manager._squad_store.get_members(squad_id)
    assert len(members) == 2
    # Agent's squad_id should be set
    agent = await agent_store.get(member_id)
    assert agent["squad_id"] == squad_id


async def test_join_requires_leader(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    outsider_id = await agent_store.create(name="outsider", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    # member cannot invite
    with pytest.raises(PermissionError, match="leader"):
        await manager.join(squad_id, outsider_id, SquadRole.MEMBER, caller_id=member_id)


async def test_leave_squad(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    await manager.leave(member_id)
    members = await manager._squad_store.get_members(squad_id)
    assert len(members) == 1
    agent = await agent_store.get(member_id)
    assert agent["squad_id"] is None


async def test_kick_member(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    await manager.kick(squad_id, member_id, caller_id=leader_id)
    members = await manager._squad_store.get_members(squad_id)
    assert len(members) == 1


async def test_kick_requires_leader(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    with pytest.raises(PermissionError, match="leader"):
        await manager.kick(squad_id, leader_id, caller_id=member_id)


async def test_set_role(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    await manager.set_role(squad_id, member_id, SquadRole.OBSERVER, caller_id=leader_id)
    role = await manager._squad_store.get_member_role(squad_id, member_id)
    assert role == "observer"


async def test_transfer_leadership(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    await manager.set_role(squad_id, member_id, SquadRole.LEADER, caller_id=leader_id)
    # Previous leader becomes member
    old_role = await manager._squad_store.get_member_role(squad_id, leader_id)
    assert old_role == "member"
    new_role = await manager._squad_store.get_member_role(squad_id, member_id)
    assert new_role == "leader"


async def test_dissolve_squad(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    await manager.dissolve(squad_id, caller_id=leader_id)
    squad = await manager._squad_store.get(squad_id)
    assert squad["status"] == "dissolved"
    # Members' squad_id should be cleared
    agent = await agent_store.get(member_id)
    assert agent["squad_id"] is None


async def test_dissolve_requires_leader(manager, agent_store):
    leader_id = await agent_store.create(name="leader", capabilities=[])
    member_id = await agent_store.create(name="member", capabilities=[])
    squad_id = await manager.create(name="team", creator_agent_id=leader_id)
    await manager.join(squad_id, member_id, SquadRole.MEMBER, caller_id=leader_id)
    with pytest.raises(PermissionError, match="leader"):
        await manager.dissolve(squad_id, caller_id=member_id)


async def test_list_squads(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    await manager.create(name="team-a", creator_agent_id=a1)
    await manager.create(name="team-b", creator_agent_id=a2)
    squads = await manager.list_squads()
    assert len(squads) == 2
