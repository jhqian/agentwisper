# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Tests for the Broker core orchestrator."""

import pytest

from broker.core import Broker
from common.config import BrokerConfig


@pytest.fixture
async def broker(tmp_path):
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    b = Broker(config)
    await b.start()
    yield b
    await b.stop()


async def test_broker_registers_agent(broker):
    result = await broker.register_agent("test-agent", ["code", "review"])
    assert "agent_id" in result
    assert result["agent_id"].startswith("agent_")


async def test_broker_gets_agent_info(broker):
    reg = await broker.register_agent("test-agent", ["code"])
    info = await broker.get_agent_info(reg["agent_id"])
    assert info["name"] == "test-agent"
    assert info["status"] == "active"


async def test_broker_lists_agents(broker):
    await broker.register_agent("a1", [])
    await broker.register_agent("a2", [])
    result = await broker.list_agents()
    assert len(result["agents"]) == 2


async def test_broker_p2p_messaging(broker):
    r1 = await broker.register_agent("sender", [])
    r2 = await broker.register_agent("receiver", [])
    msg = await broker.send_message(r1["agent_id"], r2["agent_id"], '{"hello": true}', "p2p")
    assert "msg_id" in msg
    polled = await broker.poll_messages(r2["agent_id"])
    assert len(polled["messages"]) >= 1


async def test_broker_squad_lifecycle(broker):
    r = await broker.register_agent("leader", [])
    squad = await broker.create_squad("dev-team", r["agent_id"])
    assert "squad_id" in squad
    info = await broker.get_squad_info(squad["squad_id"])
    assert info["squad"]["name"] == "dev-team"


async def test_broker_team_lifecycle(broker):
    r1 = await broker.register_agent("a1", [])
    r2 = await broker.register_agent("a2", [])
    team = await broker.form_team(r1["agent_id"], [r1["agent_id"], r2["agent_id"]], topic="review")
    assert "team_id" in team
    info = await broker.get_team_info(team["team_id"])
    assert len(info["members"]) == 2


async def test_broker_pubsub(broker):
    r1 = await broker.register_agent("pub", [])
    r2 = await broker.register_agent("sub", [])
    await broker.subscribe_topic(r2["agent_id"], "alerts")
    result = await broker.broadcast_message(r1["agent_id"], "alerts", '{"level": "high"}')
    assert result["subscriber_count"] >= 1


async def test_broker_status(broker):
    status = await broker.broker_status()
    assert status["status"] == "healthy"
    assert "active_agents" in status
    assert "pending_messages" in status
    assert "waiting_agents" in status


async def test_broker_pause_resume(broker):
    r = await broker.register_agent("test", [])
    await broker.pause_agent(r["agent_id"])
    info = await broker.get_agent_info(r["agent_id"])
    assert info["status"] == "paused"
    result = await broker.resume_agent(r["agent_id"])
    assert result["status"] == "active"


async def test_broker_deregister(broker):
    r = await broker.register_agent("test", [])
    await broker.deregister_agent(r["agent_id"])
    info = await broker.get_agent_info(r["agent_id"])
    assert info is not None
    assert info["status"] == "disconnected"


async def test_broker_send_notifies_wait_event(broker):
    r = await broker.register_agent("receiver", [])
    event = broker.register_wait(r["agent_id"])
    assert not event.is_set()
    # send_message triggers _notify_recipients which sets the event
    r1 = await broker.register_agent("sender", [])
    await broker.send_message(r1["agent_id"], r["agent_id"], "hello", "p2p")
    assert event.is_set()
    broker.unregister_wait(r["agent_id"])


async def test_broker_register_wait_and_notify(broker):
    import anyio
    r = await broker.register_agent("test", [])
    event = broker.register_wait(r["agent_id"])
    assert not event.is_set()
    assert r["agent_id"] in broker._wait_events
    event.set()
    assert event.is_set()
    broker.unregister_wait(r["agent_id"])
    assert r["agent_id"] not in broker._wait_events


async def test_broker_wake_agent(broker):
    r = await broker.register_agent("sleepy", [])
    await broker.pause_agent(r["agent_id"])
    info = await broker.get_agent_info(r["agent_id"])
    assert info["status"] == "paused"
    result = await broker.wake_agent(r["agent_id"], message="Wake up!")
    assert result["status"] == "active"
    assert result["message_queued"] is True
    info = await broker.get_agent_info(r["agent_id"])
    assert info["status"] == "active"


async def test_broker_wake_already_active_agent(broker):
    r = await broker.register_agent("active-agent", [])
    result = await broker.wake_agent(r["agent_id"], message="Hello")
    assert result["status"] == "active"
    assert result["message_queued"] is True


async def test_broker_register_duplicate_name_gets_suffix(broker):
    r1 = await broker.register_agent("dev", ["code"])
    r2 = await broker.register_agent("dev", ["test"])
    assert r1["assigned_name"] == "dev"
    assert r2["assigned_name"] == "dev-1"
    assert r1["agent_id"] != r2["agent_id"]


async def test_broker_message_wait_unblocks_on_send(broker):
    """message_wait should return immediately when message arrives."""
    r = await broker.register_agent("receiver", [])
    event = broker.register_wait(r["agent_id"])
    assert not event.is_set()
    r1 = await broker.register_agent("sender", [])
    await broker.send_message(r1["agent_id"], r["agent_id"], "hello", "p2p")
    assert event.is_set()
    broker.unregister_wait(r["agent_id"])


async def test_broker_register_with_session_name(broker):
    result = await broker.register_agent("test", ["code"], session_name="sess_123")
    assert result["agent_id"].startswith("agent_")
    info = await broker.get_agent_info(result["agent_id"])
    assert info["session_name"] == "sess_123"


async def test_broker_deregister_soft_delete(broker):
    r = await broker.register_agent("test", [])
    await broker.deregister_agent(r["agent_id"])
    info = await broker.get_agent_info(r["agent_id"])
    assert info is not None
    assert info["status"] == "disconnected"


async def test_broker_reconnect(broker):
    r = await broker.register_agent("dev", ["code"], session_name="sess_old")
    agent_id = r["agent_id"]
    await broker.deregister_agent(agent_id)
    result = await broker.reconnect_agent("dev", session_name="sess_new")
    assert result["agent_id"] == agent_id
    assert result["status"] == "active"
    info = await broker.get_agent_info(agent_id)
    assert info["status"] == "active"
    assert info["session_name"] == "sess_new"


async def test_broker_reconnect_not_found(broker):
    with pytest.raises(ValueError, match="never been registered or may have expired"):
        await broker.reconnect_agent("nonexistent", session_name="sess_1")


async def test_broker_cleanup_removes_expired_agents(tmp_path):
    """Verify broker cleanup removes expired disconnected agents."""
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    b = Broker(config)
    await b.start()

    result = await b.register_agent("old-agent", ["code"])
    await b.deregister_agent(result["agent_id"])

    # Manually age the disconnected_at timestamp
    from datetime import datetime, timezone, timedelta
    old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    from persistence.database import AsyncDatabase
    await b._db.execute(
        "UPDATE agents SET disconnected_at = ? WHERE agent_id = ?",
        (old_time, result["agent_id"]),
    )

    removed = await b._run_cleanup(ttl_days=7)
    assert removed == 1
    info = await b.get_agent_info(result["agent_id"])
    assert info is None

    await b.stop()


async def test_broker_cleanup_preserves_recent(tmp_path):
    """Verify broker cleanup keeps recently disconnected agents."""
    config = BrokerConfig(db_path=str(tmp_path / "test.db"))
    b = Broker(config)
    await b.start()

    result = await b.register_agent("recent-agent", ["code"])
    await b.deregister_agent(result["agent_id"])

    removed = await b._run_cleanup(ttl_days=7)
    assert removed == 0
    info = await b.get_agent_info(result["agent_id"])
    assert info is not None

    await b.stop()


# ---------------------------------------------------------------------------
# Broker restart tests
# ---------------------------------------------------------------------------


async def test_broker_start_resets_active_agents(tmp_path):
    """Broker restart marks all active/paused agents as disconnected."""
    db_path = str(tmp_path / "test.db")
    config = BrokerConfig(db_path=db_path)

    # First broker session: register agents
    b1 = Broker(config)
    await b1.start()
    r1 = await b1.register_agent("alice", ["code"], session_name="sess_1")
    r2 = await b1.register_agent("bob", ["review"], session_name="sess_2")
    await b1.pause_agent(r2["agent_id"])
    await b1.stop()

    # Second broker session (simulates restart): agents should be disconnected
    b2 = Broker(config)
    await b2.start()
    info1 = await b2.get_agent_info(r1["agent_id"])
    assert info1["status"] == "disconnected"
    assert info1["session_name"] is None
    info2 = await b2.get_agent_info(r2["agent_id"])
    assert info2["status"] == "disconnected"
    assert info2["session_name"] is None
    await b2.stop()


async def test_broker_start_already_disconnected_unchanged(tmp_path):
    """Already disconnected agents are not affected by broker restart."""
    db_path = str(tmp_path / "test.db")
    config = BrokerConfig(db_path=db_path)

    b1 = Broker(config)
    await b1.start()
    r = await b1.register_agent("ghost", ["code"])
    await b1.deregister_agent(r["agent_id"])
    original_info = await b1.get_agent_info(r["agent_id"])
    await b1.stop()

    b2 = Broker(config)
    await b2.start()
    info = await b2.get_agent_info(r["agent_id"])
    assert info["status"] == "disconnected"
    assert info["disconnected_at"] == original_info["disconnected_at"]
    await b2.stop()


async def test_broker_reconnect_after_restart(tmp_path):
    """Agent can reconnect after broker restart to resume operations."""
    db_path = str(tmp_path / "test.db")
    config = BrokerConfig(db_path=db_path)

    # First session: register and subscribe
    b1 = Broker(config)
    await b1.start()
    r = await b1.register_agent("dev", ["code"], session_name="sess_old")
    await b1.subscribe_topic(r["agent_id"], "alerts")
    await b1.stop()

    # Second session: reconnect
    b2 = Broker(config)
    await b2.start()
    result = await b2.reconnect_agent("dev", session_name="sess_new")
    assert result["status"] == "active"
    assert result["agent_id"] == r["agent_id"]
    info = await b2.get_agent_info(r["agent_id"])
    assert info["session_name"] == "sess_new"
    # Subscription preserved
    subs = await b2._sub_store.list_by_agent(r["agent_id"])
    assert len(subs) == 1
    await b2.stop()


async def test_broker_start_empty_db_no_error(tmp_path):
    """Broker start with empty database does not fail on agent reset."""
    config = BrokerConfig(db_path=str(tmp_path / "fresh.db"))
    b = Broker(config)
    await b.start()
    status = await b.broker_status()
    assert status["active_agents"] == 0
    await b.stop()


async def test_broker_start_idempotent(tmp_path):
    """Calling start() twice does not reset agents again."""
    db_path = str(tmp_path / "test.db")
    config = BrokerConfig(db_path=db_path)

    b1 = Broker(config)
    await b1.start()
    r = await b1.register_agent("alice", ["code"])
    await b1.stop()

    b2 = Broker(config)
    await b2.start()
    # Agent now disconnected (first start)
    info = await b2.get_agent_info(r["agent_id"])
    assert info["status"] == "disconnected"
    # Second start call is no-op due to _started flag
    await b2.start()
    info2 = await b2.get_agent_info(r["agent_id"])
    assert info2["status"] == "disconnected"
    await b2.stop()
