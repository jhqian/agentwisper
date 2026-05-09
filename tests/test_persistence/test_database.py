import pytest
from persistence.database import AsyncDatabase


@pytest.fixture
async def db(tmp_path):
    database = AsyncDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


async def test_database_creates_tables(db):
    tables = await db.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = [row["name"] for row in tables]
    assert "agents" in table_names
    assert "messages" in table_names
    assert "delivery_logs" in table_names
    assert "squads" in table_names
    assert "squad_memberships" in table_names
    assert "teams" in table_names
    assert "team_memberships" in table_names
    assert "subscriptions" in table_names


async def test_database_wal_mode(db):
    result = await db.execute_fetchall("PRAGMA journal_mode")
    assert result[0]["journal_mode"] == "wal"


async def test_database_execute(db):
    await db.execute(
        "INSERT INTO agents (agent_id, name, status, capabilities, created_at, last_heartbeat) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("agent_test", "test", "active", "[]", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    rows = await db.execute_fetchall("SELECT * FROM agents WHERE agent_id = ?", ("agent_test",))
    assert len(rows) == 1
    assert rows[0]["name"] == "test"
