# Licensed under the Apache License, Version 2.0

"""Tests for HeartbeatMonitor background task."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from broker.heartbeat import HeartbeatMonitor
from common.types import AgentStatus
from persistence.agent_store import AgentStore
from persistence.database import AsyncDatabase


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def agent_store(db):
    return AgentStore(db)


async def test_check_agents_marks_stale(db, agent_store):
    monitor = HeartbeatMonitor(db, interval=5, timeout=10)
    agent_id = await agent_store.create(name="stale", capabilities=[])
    # Manually set heartbeat to past (beyond timeout)
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    await agent_store.update_heartbeat(agent_id, stale_time)

    disconnected_count = await monitor.check_agents()
    assert disconnected_count == 1

    agent = await agent_store.get(agent_id)
    assert agent["status"] == "disconnected"


async def test_check_agents_skips_active(db, agent_store):
    monitor = HeartbeatMonitor(db, interval=5, timeout=90)
    agent_id = await agent_store.create(name="active", capabilities=[])
    # Heartbeat is recent (just created)

    disconnected_count = await monitor.check_agents()
    assert disconnected_count == 0

    agent = await agent_store.get(agent_id)
    assert agent["status"] == "active"


async def test_check_agents_skips_paused(db, agent_store):
    monitor = HeartbeatMonitor(db, interval=5, timeout=10)
    agent_id = await agent_store.create(name="paused", capabilities=[])
    await agent_store.update_status(agent_id, AgentStatus.PAUSED)
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    await agent_store.update_heartbeat(agent_id, stale_time)

    disconnected_count = await monitor.check_agents()
    assert disconnected_count == 0


async def test_check_agents_skips_already_disconnected(db, agent_store):
    monitor = HeartbeatMonitor(db, interval=5, timeout=10)
    agent_id = await agent_store.create(name="disc", capabilities=[])
    await agent_store.update_status(agent_id, AgentStatus.DISCONNECTED)
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    await agent_store.update_heartbeat(agent_id, stale_time)

    disconnected_count = await monitor.check_agents()
    assert disconnected_count == 0


async def test_start_and_stop(db):
    monitor = HeartbeatMonitor(db, interval=1, timeout=90)
    await monitor.start()
    assert monitor._running is True
    await asyncio.sleep(0.2)
    await monitor.stop()
    assert monitor._running is False
