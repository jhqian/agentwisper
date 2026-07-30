from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import asyncio

logger = logging.getLogger(__name__)

_WRITE_RETRY_ATTEMPTS = 3
_WRITE_RETRY_DELAY_S = 0.1


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    capabilities TEXT NOT NULL DEFAULT '[]',
    squad_id TEXT,
    current_team_id TEXT,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    session_name TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    disconnected_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    msg_id TEXT PRIMARY KEY,
    sender_id TEXT NOT NULL,
    recipient_id TEXT,
    topic TEXT,
    msg_type TEXT NOT NULL,
    squad_id TEXT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    parent_msg_id TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS delivery_logs (
    delivery_id TEXT PRIMARY KEY,
    msg_id TEXT NOT NULL REFERENCES messages(msg_id),
    recipient_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    delivered_at TEXT
);

CREATE TABLE IF NOT EXISTS squads (
    squad_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    dissolved_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS squad_memberships (
    squad_id TEXT NOT NULL REFERENCES squads(squad_id),
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    joined_at TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    PRIMARY KEY (squad_id, agent_id)
);

CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY,
    topic TEXT,
    initiator_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    ttl_seconds INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    dismissed_at TEXT
);

CREATE TABLE IF NOT EXISTS team_memberships (
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (team_id, agent_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    sub_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    topic TEXT NOT NULL,
    squad_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id);
CREATE INDEX IF NOT EXISTS idx_messages_topic ON messages(topic);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_msg_id);
CREATE INDEX IF NOT EXISTS idx_delivery_msg ON delivery_logs(msg_id);
CREATE INDEX IF NOT EXISTS idx_delivery_recipient ON delivery_logs(recipient_id);
CREATE INDEX IF NOT EXISTS idx_delivery_status ON delivery_logs(status);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_squad ON agents(squad_id);
CREATE INDEX IF NOT EXISTS idx_agents_team ON agents(current_team_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_agent ON subscriptions(agent_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_topic ON subscriptions(topic);
CREATE INDEX IF NOT EXISTS idx_squad_memberships_agent ON squad_memberships(agent_id);
CREATE INDEX IF NOT EXISTS idx_team_memberships_agent ON team_memberships(agent_id);
"""

MIGRATIONS = [
    # Migration 1: add session_name column and UNIQUE constraint on name
    """
    ALTER TABLE agents ADD COLUMN session_name TEXT;
    DROP INDEX IF EXISTS idx_agents_name;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_name_unique ON agents(name) WHERE status != 'disconnected';
    """,
    # Migration 2: add disconnected_at column for TTL cleanup
    """
    ALTER TABLE agents ADD COLUMN disconnected_at TEXT;
    """,
    # Migration 3: rename last_heartbeat to last_seen
    """
    ALTER TABLE agents RENAME COLUMN last_heartbeat TO last_seen;
    """,
    # Migration 4: enforce full name uniqueness (including disconnected)
    """
    DROP INDEX IF EXISTS idx_agents_name_unique;
    DELETE FROM delivery_logs WHERE recipient_id IN (
        SELECT a.agent_id FROM agents a
        INNER JOIN agents b ON a.name = b.name
            AND (a.last_seen < b.last_seen OR (a.last_seen = b.last_seen AND a.rowid < b.rowid))
    );
    DELETE FROM subscriptions WHERE agent_id IN (
        SELECT a.agent_id FROM agents a
        INNER JOIN agents b ON a.name = b.name
            AND (a.last_seen < b.last_seen OR (a.last_seen = b.last_seen AND a.rowid < b.rowid))
    );
    DELETE FROM squad_memberships WHERE agent_id IN (
        SELECT a.agent_id FROM agents a
        INNER JOIN agents b ON a.name = b.name
            AND (a.last_seen < b.last_seen OR (a.last_seen = b.last_seen AND a.rowid < b.rowid))
    );
    DELETE FROM team_memberships WHERE agent_id IN (
        SELECT a.agent_id FROM agents a
        INNER JOIN agents b ON a.name = b.name
            AND (a.last_seen < b.last_seen OR (a.last_seen = b.last_seen AND a.rowid < b.rowid))
    );
    DELETE FROM agents WHERE agent_id IN (
        SELECT a.agent_id FROM agents a
        INNER JOIN agents b ON a.name = b.name
            AND (a.last_seen < b.last_seen OR (a.last_seen = b.last_seen AND a.rowid < b.rowid))
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
    """,
]


class AsyncDatabase:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._loop: asyncio.AbstractEventLoop = None  # type: ignore[assignment]
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        self._loop = asyncio.get_running_loop()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        await self._run_in_thread(self._init_db)

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA_SQL)
        # Fresh databases get the full schema above; set version so
        # migrations targeting older schemas are skipped.
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version == 0 and len(MIGRATIONS) > 0:
            conn.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")
        else:
            for i in range(current_version, len(MIGRATIONS)):
                conn.executescript(MIGRATIONS[i])
                conn.execute(f"PRAGMA user_version = {i + 1}")
        conn.commit()
        conn.close()

    async def close(self) -> None:
        pass

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self._write_lock:
            await self._run_in_thread(self._execute, sql, params)

    async def execute_fetchall(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        return await self._run_in_thread(self._fetchall, sql, params)

    async def execute_fetchone(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        rows = await self.execute_fetchall(sql, params)
        return rows[0] if rows else None

    async def execute_many(
        self, sql: str, params_list: list[tuple[Any, ...]]
    ) -> None:
        async with self._write_lock:
            await self._run_in_thread(self._execute_many, sql, params_list)

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        conn = None
        for attempt in range(1, _WRITE_RETRY_ATTEMPTS + 1):
            try:
                conn = sqlite3.connect(self._db_path, timeout=30)
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute(sql, params)
                conn.commit()
                conn.close()
                conn = None
                return
            except sqlite3.OperationalError as e:
                if conn:
                    conn.close()
                    conn = None
                if "locked" in str(e).lower() and attempt < _WRITE_RETRY_ATTEMPTS:
                    logger.debug(
                        "DB write locked (attempt %d/%d), retrying: %s",
                        attempt, _WRITE_RETRY_ATTEMPTS, e,
                    )
                    time.sleep(_WRITE_RETRY_DELAY_S * attempt)
                    continue
                raise

    def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self._db_path, timeout=30)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def _execute_many(
        self, sql: str, params_list: list[tuple[Any, ...]]
    ) -> None:
        conn = None
        for attempt in range(1, _WRITE_RETRY_ATTEMPTS + 1):
            try:
                conn = sqlite3.connect(self._db_path, timeout=30)
                conn.execute("PRAGMA foreign_keys=ON")
                conn.executemany(sql, params_list)
                conn.commit()
                conn.close()
                conn = None
                return
            except sqlite3.OperationalError as e:
                if conn:
                    conn.close()
                    conn = None
                if "locked" in str(e).lower() and attempt < _WRITE_RETRY_ATTEMPTS:
                    logger.debug(
                        "DB batch write locked (attempt %d/%d), retrying: %s",
                        attempt, _WRITE_RETRY_ATTEMPTS, e,
                    )
                    time.sleep(_WRITE_RETRY_DELAY_S * attempt)
                    continue
                raise

    async def _run_in_thread(self, fn, *args):
        return await self._loop.run_in_executor(None, fn, *args)
