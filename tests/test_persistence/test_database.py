import pytest
from agentwisper.persistence.database import AsyncDatabase, MIGRATIONS


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
        "INSERT INTO agents (agent_id, name, status, created_at, last_seen) "
        "VALUES (?, ?, ?, ?, ?)",
        ("agent_test", "test", "active", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    rows = await db.execute_fetchall("SELECT * FROM agents WHERE agent_id = ?", ("agent_test",))
    assert len(rows) == 1
    assert rows[0]["name"] == "test"


async def test_session_name_column_exists(db):
    await db.execute(
        "INSERT INTO agents (agent_id, name, status, created_at, last_seen, session_name) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("agent_sn", "sn-test", "active", "2026-01-01", "2026-01-01", "session_123"),
    )
    row = await db.execute_fetchone("SELECT session_name FROM agents WHERE agent_id = ?", ("agent_sn",))
    assert row["session_name"] == "session_123"


async def test_unique_name_constraint(db):
    await db.execute(
        "INSERT INTO agents (agent_id, name, status, created_at, last_seen) "
        "VALUES (?, ?, ?, ?, ?)",
        ("agent_1", "dev", "active", "2026-01-01", "2026-01-01"),
    )
    with pytest.raises(Exception):
        await db.execute(
            "INSERT INTO agents (agent_id, name, status, created_at, last_seen) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agent_2", "dev", "active", "2026-01-01", "2026-01-01"),
        )


async def test_migration_version(db):
    version = await db.execute_fetchone("PRAGMA user_version")
    assert version["user_version"] == len(MIGRATIONS)


async def test_agents_table_has_disconnected_at_column(db):
    columns = await db.execute_fetchall("PRAGMA table_info(agents)")
    column_names = [c["name"] for c in columns]
    assert "disconnected_at" in column_names


async def test_migration_drops_capabilities_column(tmp_path):
    """Old DB with a capabilities column upgrades: column dropped, data kept."""
    import sqlite3
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 4")
    conn.execute(
        "CREATE TABLE agents ("
        "agent_id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'active', "
        "capabilities TEXT NOT NULL DEFAULT '[]', "
        "created_at TEXT NOT NULL, last_seen TEXT NOT NULL, "
        "session_name TEXT, disconnected_at TEXT, "
        "metadata TEXT NOT NULL DEFAULT '{}', "
        "squad_id TEXT, current_team_id TEXT)"
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_name ON agents(name)")
    conn.execute(
        "INSERT INTO agents (agent_id, name, status, capabilities, created_at, last_seen) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("agent_old", "old-agent", "active", '["code"]', "2026-01-01", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    db = AsyncDatabase(db_path)
    await db.initialize()
    cols = await db.execute_fetchall("PRAGMA table_info(agents)")
    assert "capabilities" not in [c["name"] for c in cols]
    row = await db.execute_fetchone("SELECT name FROM agents WHERE agent_id = ?", ("agent_old",))
    assert row["name"] == "old-agent"
    version = await db.execute_fetchone("PRAGMA user_version")
    assert version["user_version"] == len(MIGRATIONS)
    await db.close()
