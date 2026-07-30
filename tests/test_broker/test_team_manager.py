# Copyright 2026 agentwisper contributors
#
# Licensed under the Apache License, Version 2.0

import pytest
from agentwisper.broker.team_manager import TeamManager
from agentwisper.persistence.database import AsyncDatabase
from agentwisper.persistence.agent_store import AgentStore


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def manager(db):
    return TeamManager(db)


@pytest.fixture
async def agent_store(db):
    return AgentStore(db)


async def test_form_team(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    team_id = await manager.form(initiator_id=a1, agent_ids=[a1, a2], topic="code-review")
    assert team_id.startswith("team_")
    info = await manager.get_info(team_id)
    assert info["team"]["topic"] == "code-review"
    assert info["team"]["initiator_id"] == a1
    assert len(info["members"]) == 2


async def test_form_sets_team_id(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    team_id = await manager.form(initiator_id=a1, agent_ids=[a1, a2])
    agent = await agent_store.get(a1)
    assert agent["current_team_id"] == team_id


async def test_form_rejects_agent_already_in_team(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    a3 = await agent_store.create(name="a3", capabilities=[])
    await manager.form(initiator_id=a1, agent_ids=[a1, a2])
    with pytest.raises(ValueError, match="already in a team"):
        await manager.form(initiator_id=a3, agent_ids=[a2, a3])


async def test_dismiss_team(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    team_id = await manager.form(initiator_id=a1, agent_ids=[a1, a2])
    await manager.dismiss(team_id, caller_id=a1)
    info = await manager.get_info(team_id)
    assert info["team"]["status"] == "dismissed"
    # Agents' current_team_id should be cleared
    agent = await agent_store.get(a1)
    assert agent["current_team_id"] is None


async def test_dismiss_any_member(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    team_id = await manager.form(initiator_id=a1, agent_ids=[a1, a2])
    await manager.dismiss(team_id, caller_id=a2)
    info = await manager.get_info(team_id)
    assert info["team"]["status"] == "dismissed"


async def test_dismiss_non_member_fails(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    a3 = await agent_store.create(name="a3", capabilities=[])
    team_id = await manager.form(initiator_id=a1, agent_ids=[a1, a2])
    with pytest.raises(PermissionError, match="member"):
        await manager.dismiss(team_id, caller_id=a3)


async def test_form_with_ttl(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    team_id = await manager.form(initiator_id=a1, agent_ids=[a1], ttl_seconds=3600)
    info = await manager.get_info(team_id)
    assert info["team"]["ttl_seconds"] == 3600
    assert info["team"]["expires_at"] is not None


async def test_list_teams(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    await manager.form(initiator_id=a1, agent_ids=[a1])
    await manager.form(initiator_id=a2, agent_ids=[a2])
    teams = await manager.list_teams()
    assert len(teams) == 2


async def test_list_teams_by_agent(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    a2 = await agent_store.create(name="a2", capabilities=[])
    await manager.form(initiator_id=a1, agent_ids=[a1, a2])
    teams = await manager.list_teams(agent_id=a1)
    assert len(teams) == 1


async def test_expire_teams(manager, agent_store):
    a1 = await agent_store.create(name="a1", capabilities=[])
    team_id = await manager.form(initiator_id=a1, agent_ids=[a1], ttl_seconds=1)
    # Manually set expires_at to past
    await manager._team_store._db.execute(
        "UPDATE teams SET expires_at = '2020-01-01T00:00:00Z' WHERE team_id = ?",
        (team_id,)
    )
    count = await manager.expire_teams()
    assert count == 1
    info = await manager.get_info(team_id)
    assert info["team"]["status"] == "expired"
    agent = await agent_store.get(a1)
    assert agent["current_team_id"] is None
