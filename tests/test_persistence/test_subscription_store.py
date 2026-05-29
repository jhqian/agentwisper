# Copyright 2026 agentsquad contributors
#
# Licensed under the Apache License, Version 2.0

import pytest
from persistence.subscription_store import SubscriptionStore
from persistence.agent_store import AgentStore


@pytest.fixture
async def store(db):
    return SubscriptionStore(db)


@pytest.fixture
async def agent_store(db):
    return AgentStore(db)


async def test_create_subscription(store, agent_store):
    a1 = await agent_store.create(name="sub1", capabilities=[])
    sub_id = await store.create(agent_id=a1, topic="alerts")
    assert sub_id.startswith("sub_")


async def test_delete_subscription(store, agent_store):
    a1 = await agent_store.create(name="sub1", capabilities=[])
    sub_id = await store.create(agent_id=a1, topic="alerts")
    await store.delete(sub_id)
    subs = await store.list_by_agent(a1)
    assert len(subs) == 0


async def test_get_subscribers(store, agent_store):
    a1 = await agent_store.create(name="sub1", capabilities=[])
    a2 = await agent_store.create(name="sub2", capabilities=[])
    await store.create(agent_id=a1, topic="deploy")
    await store.create(agent_id=a2, topic="deploy")
    subscribers = await store.get_subscribers("deploy")
    assert len(subscribers) == 2
    assert a1 in subscribers
    assert a2 in subscribers


async def test_get_subscribers_squad_scoped(store, agent_store):
    a1 = await agent_store.create(name="sub1", capabilities=[])
    a2 = await agent_store.create(name="sub2", capabilities=[])
    await store.create(agent_id=a1, topic="deploy", squad_id="squad_x")
    await store.create(agent_id=a2, topic="deploy", squad_id="squad_y")
    subscribers = await store.get_subscribers("deploy", squad_id="squad_x")
    assert len(subscribers) == 1
    assert a1 in subscribers


async def test_list_by_agent(store, agent_store):
    a1 = await agent_store.create(name="sub1", capabilities=[])
    await store.create(agent_id=a1, topic="alerts")
    await store.create(agent_id=a1, topic="deploy")
    subs = await store.list_by_agent(a1)
    assert len(subs) == 2


async def test_get_subscribers_excludes_disconnected(store, agent_store):
    from common.types import AgentStatus
    a1 = await agent_store.create(name="sub1", capabilities=[])
    a2 = await agent_store.create(name="sub2", capabilities=[])
    await store.create(agent_id=a1, topic="deploy")
    await store.create(agent_id=a2, topic="deploy")
    await agent_store.update_status(a2, AgentStatus.DISCONNECTED)
    subscribers = await store.get_subscribers("deploy")
    assert len(subscribers) == 1
    assert a1 in subscribers
    assert a2 not in subscribers


async def test_get_subscribers_squad_scoped_excludes_disconnected(store, agent_store):
    from common.types import AgentStatus
    a1 = await agent_store.create(name="sub1", capabilities=[])
    a2 = await agent_store.create(name="sub2", capabilities=[])
    await store.create(agent_id=a1, topic="deploy", squad_id="squad_x")
    await store.create(agent_id=a2, topic="deploy", squad_id="squad_x")
    await agent_store.update_status(a2, AgentStatus.DISCONNECTED)
    subscribers = await store.get_subscribers("deploy", squad_id="squad_x")
    assert len(subscribers) == 1
    assert a1 in subscribers
