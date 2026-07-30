# Copyright 2026 agentsquad contributors
#
# Licensed under the Apache License, Version 2.0

"""Subscription store providing CRUD and lookup operations for subscriptions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from agentsquad.persistence.database import AsyncDatabase


def _generate_sub_id() -> str:
    return f"sub_{uuid.uuid4().hex[:20]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubscriptionStore:
    """Wraps AsyncDatabase to provide subscription persistence operations."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def create(
        self,
        agent_id: str,
        topic: str,
        squad_id: str | None = None,
    ) -> str:
        """Create a new subscription. Returns the generated sub_id."""
        sub_id = _generate_sub_id()
        await self._db.execute(
            "INSERT INTO subscriptions (sub_id, agent_id, topic, squad_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sub_id, agent_id, topic, squad_id, _now_iso()),
        )
        return sub_id

    async def delete(self, sub_id: str) -> None:
        """Delete a subscription by ID."""
        await self._db.execute(
            "DELETE FROM subscriptions WHERE sub_id = ?", (sub_id,)
        )

    async def delete_by_agent(self, agent_id: str) -> int:
        """Delete all subscriptions for an agent. Returns count deleted."""
        result = await self._db.execute_fetchall(
            "SELECT sub_id FROM subscriptions WHERE agent_id = ?", (agent_id,)
        )
        if not result:
            return 0
        await self._db.execute(
            "DELETE FROM subscriptions WHERE agent_id = ?", (agent_id,)
        )
        return len(result)

    async def get_subscribers(
        self, topic: str, squad_id: str | None = None
    ) -> list[str]:
        """Get agent_ids subscribed to a topic, excluding disconnected agents."""
        if squad_id is not None:
            rows = await self._db.execute_fetchall(
                "SELECT s.agent_id FROM subscriptions s "
                "JOIN agents a ON s.agent_id = a.agent_id "
                "WHERE s.topic = ? AND s.squad_id = ? AND a.status != 'disconnected'",
                (topic, squad_id),
            )
        else:
            rows = await self._db.execute_fetchall(
                "SELECT s.agent_id FROM subscriptions s "
                "JOIN agents a ON s.agent_id = a.agent_id "
                "WHERE s.topic = ? AND a.status != 'disconnected'",
                (topic,),
            )
        return [row["agent_id"] for row in rows]

    async def list_by_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """List all subscriptions for a given agent."""
        return await self._db.execute_fetchall(
            "SELECT * FROM subscriptions WHERE agent_id = ? ORDER BY created_at",
            (agent_id,),
        )
