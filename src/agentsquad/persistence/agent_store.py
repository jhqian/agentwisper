# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Agent store providing CRUD and lifecycle operations for agents."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from agentsquad.common.types import AgentStatus
from agentsquad.persistence.database import AsyncDatabase


def _generate_agent_id() -> str:
    return f"agent_{uuid.uuid4().hex[:20]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentStore:
    """Wraps AsyncDatabase to provide agent persistence operations."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def create(
        self,
        name: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
        session_name: str | None = None,
    ) -> str:
        """Create a new agent record. Returns the generated agent_id."""
        agent_id = _generate_agent_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO agents (agent_id, name, status, capabilities, created_at, last_seen, session_name, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                agent_id,
                name,
                AgentStatus.ACTIVE,
                json.dumps(capabilities),
                now,
                now,
                session_name,
                json.dumps(metadata or {}),
            ),
        )
        return agent_id

    async def get(self, agent_id: str) -> dict[str, Any] | None:
        """Retrieve an agent by ID. Returns None if not found."""
        return await self._db.execute_fetchone(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        )

    async def get_by_name(self, name: str) -> dict[str, Any] | None:
        """Retrieve an agent by name, preferring active agents. Returns None if not found."""
        return await self._db.execute_fetchone(
            "SELECT * FROM agents WHERE name = ? "
            "ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, last_seen DESC "
            "LIMIT 1",
            (name,),
        )

    async def update_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update agent status and track disconnection time."""
        if status == AgentStatus.DISCONNECTED:
            await self._db.execute(
                "UPDATE agents SET status = ?, disconnected_at = ? WHERE agent_id = ?",
                (status, _now_iso(), agent_id),
            )
        else:
            await self._db.execute(
                "UPDATE agents SET status = ?, disconnected_at = NULL WHERE agent_id = ?",
                (status, agent_id),
            )

    async def update_session_name(self, agent_id: str, session_name: str | None) -> None:
        """Update agent session_name."""
        await self._db.execute(
            "UPDATE agents SET session_name = ? WHERE agent_id = ?",
            (session_name, agent_id),
        )

    async def update_status_and_session(
        self, agent_id: str, name: str, status: AgentStatus, session_name: str | None
    ) -> int:
        """Atomic credential verify + status/session update.

        Verifies both agent_id AND name match before updating.
        Returns 1 if updated (credentials match), 0 otherwise.
        """
        now = _now_iso()
        await self._db.execute(
            "UPDATE agents SET status = ?, last_seen = ?, session_name = ?, "
            "disconnected_at = NULL WHERE agent_id = ? AND name = ?",
            (status, now, session_name, agent_id, name),
        )
        check = await self._db.execute_fetchone(
            "SELECT agent_id FROM agents WHERE agent_id = ? AND name = ? AND status = ?",
            (agent_id, name, status),
        )
        return 1 if check is not None else 0

    async def update_last_seen(self, agent_id: str) -> None:
        """Update agent last_seen timestamp to now."""
        await self._db.execute(
            "UPDATE agents SET last_seen = ? WHERE agent_id = ?",
            (_now_iso(), agent_id),
        )

    async def get_disconnected_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a disconnected agent by exact name."""
        return await self._db.execute_fetchone(
            "SELECT * FROM agents WHERE name = ? AND status = ?",
            (name, AgentStatus.DISCONNECTED),
        )

    async def set_squad(self, agent_id: str, squad_id: str | None) -> None:
        """Assign or clear agent squad membership."""
        await self._db.execute(
            "UPDATE agents SET squad_id = ? WHERE agent_id = ?",
            (squad_id, agent_id),
        )

    async def set_team(self, agent_id: str, team_id: str | None) -> None:
        """Assign or clear agent team membership."""
        await self._db.execute(
            "UPDATE agents SET current_team_id = ? WHERE agent_id = ?",
            (team_id, agent_id),
        )

    async def delete(self, agent_id: str) -> None:
        """Delete an agent record."""
        await self._db.execute(
            "DELETE FROM agents WHERE agent_id = ?", (agent_id,)
        )

    async def cleanup_expired_agents(self, ttl_days: int) -> int:
        """Hard-delete disconnected agents older than ttl_days.

        Cascades to memberships, subscriptions, messages, and delivery logs.
        Returns count of removed agents.
        """
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
        expired = await self._db.execute_fetchall(
            "SELECT agent_id FROM agents WHERE status = ? AND disconnected_at < ?",
            (AgentStatus.DISCONNECTED, cutoff),
        )
        if not expired:
            return 0

        ids = [row["agent_id"] for row in expired]
        ph = ",".join("?" * len(ids))

        # Re-check status to avoid TOCTOU: an agent may have been
        # reconnected between the initial SELECT and now. Only delete
        # resources for agents that are still disconnected.
        still = await self._db.execute_fetchall(
            f"SELECT agent_id FROM agents WHERE agent_id IN ({ph}) "
            f"AND status = ?",
            tuple(ids) + (AgentStatus.DISCONNECTED,),
        )
        safe_ids = [row["agent_id"] for row in still]
        if not safe_ids:
            return 0

        safe_ph = ",".join("?" * len(safe_ids))
        await self._db.execute(
            f"DELETE FROM squad_memberships WHERE agent_id IN ({safe_ph})",
            tuple(safe_ids),
        )
        await self._db.execute(
            f"DELETE FROM team_memberships WHERE agent_id IN ({safe_ph})",
            tuple(safe_ids),
        )
        await self._db.execute(
            f"DELETE FROM subscriptions WHERE agent_id IN ({safe_ph})",
            tuple(safe_ids),
        )
        await self._db.execute(
            f"DELETE FROM delivery_logs WHERE recipient_id IN ({safe_ph})",
            tuple(safe_ids),
        )
        await self._db.execute(
            f"DELETE FROM messages WHERE sender_id IN ({safe_ph}) "
            f"OR recipient_id IN ({safe_ph})",
            tuple(safe_ids) + tuple(safe_ids),
        )
        await self._db.execute(
            f"DELETE FROM agents WHERE agent_id IN ({safe_ph})",
            tuple(safe_ids),
        )
        return len(safe_ids)

    async def list_all(self) -> list[dict[str, Any]]:
        """List all agents ordered by creation time."""
        return await self._db.execute_fetchall(
            "SELECT * FROM agents ORDER BY created_at"
        )

    async def list_by_squad(self, squad_id: str) -> list[dict[str, Any]]:
        """List all agents in a given squad ordered by creation time."""
        return await self._db.execute_fetchall(
            "SELECT * FROM agents WHERE squad_id = ? ORDER BY created_at",
            (squad_id,),
        )

    async def list_active(self) -> list[dict[str, Any]]:
        """List active (connected) agents ordered by creation time."""
        return await self._db.execute_fetchall(
            "SELECT * FROM agents WHERE status = ? ORDER BY created_at",
            (AgentStatus.ACTIVE,),
        )
