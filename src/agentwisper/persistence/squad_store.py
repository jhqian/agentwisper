# Copyright 2026 agentwisper contributors
#
# Licensed under the Apache License, Version 2.0

"""Squad store providing CRUD and membership operations for squads."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from agentwisper.persistence.database import AsyncDatabase


def _generate_squad_id() -> str:
    return f"squad_{uuid.uuid4().hex[:20]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SquadStore:
    """Wraps AsyncDatabase to provide squad persistence operations."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def create(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new squad. Returns the generated squad_id."""
        squad_id = _generate_squad_id()
        now = _now_iso()
        await self._db.execute(
            "INSERT INTO squads (squad_id, name, status, created_at, dissolved_at, metadata) "
            "VALUES (?, ?, 'active', ?, NULL, ?)",
            (squad_id, name, now, json.dumps(metadata or {})),
        )
        return squad_id

    async def get(self, squad_id: str) -> dict[str, Any] | None:
        """Retrieve a squad by ID. Returns None if not found."""
        return await self._db.execute_fetchone(
            "SELECT * FROM squads WHERE squad_id = ?", (squad_id,)
        )

    async def list_active(self) -> list[dict[str, Any]]:
        """List all active squads ordered by creation time."""
        return await self._db.execute_fetchall(
            "SELECT * FROM squads WHERE status = 'active' ORDER BY created_at"
        )

    async def dissolve(self, squad_id: str) -> None:
        """Dissolve a squad. Sets status='dissolved' and dissolved_at=now."""
        await self._db.execute(
            "UPDATE squads SET status = 'dissolved', dissolved_at = ? WHERE squad_id = ?",
            (_now_iso(), squad_id),
        )

    async def add_member(
        self, squad_id: str, agent_id: str, role: str
    ) -> None:
        """Add an agent to a squad with a given role."""
        await self._db.execute(
            "INSERT INTO squad_memberships (squad_id, agent_id, joined_at, role) "
            "VALUES (?, ?, ?, ?)",
            (squad_id, agent_id, _now_iso(), role),
        )

    async def remove_member(self, squad_id: str, agent_id: str) -> None:
        """Remove an agent from a squad."""
        await self._db.execute(
            "DELETE FROM squad_memberships WHERE squad_id = ? AND agent_id = ?",
            (squad_id, agent_id),
        )

    async def get_members(self, squad_id: str) -> list[dict[str, Any]]:
        """Get all members of a squad."""
        return await self._db.execute_fetchall(
            "SELECT * FROM squad_memberships WHERE squad_id = ?",
            (squad_id,),
        )

    async def get_member_role(
        self, squad_id: str, agent_id: str
    ) -> str | None:
        """Get the role of a specific member in a squad. Returns None if not a member."""
        row = await self._db.execute_fetchone(
            "SELECT role FROM squad_memberships WHERE squad_id = ? AND agent_id = ?",
            (squad_id, agent_id),
        )
        return row["role"] if row else None

    async def set_member_role(
        self, squad_id: str, agent_id: str, role: str
    ) -> None:
        """Update the role of a member in a squad."""
        await self._db.execute(
            "UPDATE squad_memberships SET role = ? WHERE squad_id = ? AND agent_id = ?",
            (role, squad_id, agent_id),
        )
