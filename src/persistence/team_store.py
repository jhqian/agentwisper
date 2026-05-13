# Copyright 2026 agentsquad contributors
#
# Licensed under the Apache License, Version 2.0

"""Team store providing CRUD and membership operations for teams."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from persistence.database import AsyncDatabase


def _generate_team_id() -> str:
    return f"team_{uuid.uuid4().hex[:20]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TeamStore:
    """Wraps AsyncDatabase to provide team persistence operations."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def create(
        self,
        initiator_id: str,
        agent_ids: list[str],
        topic: str | None = None,
        ttl_seconds: int | None = None,
    ) -> str:
        """Create a new team with memberships for all agents. Returns the generated team_id."""
        team_id = _generate_team_id()
        now = _now_iso()

        expires_at = None
        if ttl_seconds is not None:
            from datetime import timedelta
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            ).isoformat()

        await self._db.execute(
            "INSERT INTO teams (team_id, topic, initiator_id, status, ttl_seconds, "
            "created_at, expires_at, dismissed_at) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?, NULL)",
            (team_id, topic, initiator_id, ttl_seconds, now, expires_at),
        )

        # Insert memberships for all agents
        membership_params = [
            (team_id, agent_id, now) for agent_id in agent_ids
        ]
        await self._db.execute_many(
            "INSERT INTO team_memberships (team_id, agent_id, joined_at) "
            "VALUES (?, ?, ?)",
            membership_params,
        )

        return team_id

    async def get(self, team_id: str) -> dict[str, Any] | None:
        """Retrieve a team by ID. Returns None if not found."""
        return await self._db.execute_fetchone(
            "SELECT * FROM teams WHERE team_id = ?", (team_id,)
        )

    async def list_active(self) -> list[dict[str, Any]]:
        """List all active teams ordered by creation time."""
        return await self._db.execute_fetchall(
            "SELECT * FROM teams WHERE status = 'active' ORDER BY created_at"
        )

    async def list_by_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """List all teams an agent belongs to."""
        return await self._db.execute_fetchall(
            "SELECT t.* FROM teams t "
            "JOIN team_memberships tm ON t.team_id = tm.team_id "
            "WHERE tm.agent_id = ? ORDER BY t.created_at",
            (agent_id,),
        )

    async def dismiss(self, team_id: str) -> None:
        """Dismiss a team. Sets status='dismissed' and dismissed_at=now."""
        await self._db.execute(
            "UPDATE teams SET status = 'dismissed', dismissed_at = ? WHERE team_id = ?",
            (_now_iso(), team_id),
        )

    async def expire_expired_teams(self) -> int:
        """Mark expired teams as 'expired'. Returns count of expired teams."""
        now = _now_iso()
        await self._db.execute(
            "UPDATE teams SET status = 'expired' "
            "WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        # Count how many were just expired
        result = await self._db.execute_fetchone(
            "SELECT COUNT(*) as cnt FROM teams WHERE status = 'expired' AND expires_at < ?",
            (now,),
        )
        return result["cnt"] if result else 0

    async def get_members(self, team_id: str) -> list[dict[str, Any]]:
        """Get all members of a team."""
        return await self._db.execute_fetchall(
            "SELECT * FROM team_memberships WHERE team_id = ?",
            (team_id,),
        )
