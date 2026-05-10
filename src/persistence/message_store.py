# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Message store providing CRUD, delivery log fan-out, and query operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from persistence.database import AsyncDatabase
from common.types import MessageType, MessageStatus


def _generate_msg_id() -> str:
    return f"msg_{uuid.uuid4().hex[:20]}"


def _generate_delivery_id() -> str:
    return f"dlv_{uuid.uuid4().hex[:20]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageStore:
    """Wraps AsyncDatabase to provide message persistence operations."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def create(
        self,
        sender_id: str,
        recipient_id: str | None,
        msg_type: MessageType,
        payload: str,
        topic: str | None = None,
        squad_id: str | None = None,
        parent_msg_id: str | None = None,
        expires_at: str | None = None,
    ) -> str:
        """Create a new message record. Returns the generated msg_id."""
        msg_id = _generate_msg_id()
        await self._db.execute(
            "INSERT INTO messages "
            "(msg_id, sender_id, recipient_id, topic, msg_type, squad_id, payload, "
            "status, parent_msg_id, created_at, delivered_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
            (msg_id, sender_id, recipient_id, topic, msg_type, squad_id,
             payload, MessageStatus.PENDING, parent_msg_id, _now_iso(), expires_at),
        )
        return msg_id

    async def get(self, msg_id: str) -> dict[str, Any] | None:
        """Retrieve a message by ID. Returns None if not found."""
        return await self._db.execute_fetchone(
            "SELECT * FROM messages WHERE msg_id = ?", (msg_id,)
        )

    async def get_pending_for_agent(
        self, agent_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Retrieve all pending messages for a given agent."""
        return await self._db.execute_fetchall(
            "SELECT * FROM messages WHERE recipient_id = ? AND status = 'pending' "
            "ORDER BY created_at LIMIT ?",
            (agent_id, limit),
        )

    async def mark_delivered(self, msg_id: str) -> None:
        """Mark a message as delivered with current timestamp."""
        await self._db.execute(
            "UPDATE messages SET status = ?, delivered_at = ? WHERE msg_id = ?",
            (MessageStatus.DELIVERED, _now_iso(), msg_id),
        )

    async def mark_acknowledged(self, msg_id: str) -> None:
        """Mark a message as acknowledged."""
        await self._db.execute(
            "UPDATE messages SET status = ? WHERE msg_id = ?",
            (MessageStatus.ACKNOWLEDGED, msg_id),
        )

    async def mark_failed(self, msg_id: str) -> None:
        """Mark a message as failed."""
        await self._db.execute(
            "UPDATE messages SET status = ? WHERE msg_id = ?",
            (MessageStatus.FAILED, msg_id),
        )

    async def create_delivery_logs(
        self, msg_id: str, recipient_ids: list[str]
    ) -> None:
        """Create delivery log entries for fan-out (Pub/Sub)."""
        if not recipient_ids:
            return
        params_list = [
            (_generate_delivery_id(), msg_id, rid, MessageStatus.PENDING, None)
            for rid in recipient_ids
        ]
        await self._db.execute_many(
            "INSERT INTO delivery_logs (delivery_id, msg_id, recipient_id, status, delivered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            params_list,
        )

    async def get_pending_deliveries(
        self, agent_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Retrieve pending delivery logs for an agent, joined with message data."""
        return await self._db.execute_fetchall(
            "SELECT dl.*, m.sender_id, m.topic, m.msg_type, m.payload, m.squad_id, "
            "m.parent_msg_id, m.created_at as msg_created_at "
            "FROM delivery_logs dl JOIN messages m ON dl.msg_id = m.msg_id "
            "WHERE dl.recipient_id = ? AND dl.status = 'pending' "
            "ORDER BY m.created_at LIMIT ?",
            (agent_id, limit),
        )

    async def mark_delivery_delivered(self, delivery_id: str) -> None:
        """Mark a delivery log entry as delivered."""
        await self._db.execute(
            "UPDATE delivery_logs SET status = ?, delivered_at = ? WHERE delivery_id = ?",
            (MessageStatus.DELIVERED, _now_iso(), delivery_id),
        )

    async def mark_delivery_acknowledged(self, delivery_id: str) -> None:
        """Mark a delivery log entry as acknowledged."""
        await self._db.execute(
            "UPDATE delivery_logs SET status = ? WHERE delivery_id = ?",
            (MessageStatus.ACKNOWLEDGED, delivery_id),
        )

    async def query(
        self,
        sender_id: str | None = None,
        recipient_id: str | None = None,
        topic: str | None = None,
        msg_type: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query messages with flexible filtering."""
        conditions: list[str] = []
        params: list[Any] = []
        if sender_id:
            conditions.append("sender_id = ?")
            params.append(sender_id)
        if recipient_id:
            conditions.append("recipient_id = ?")
            params.append(recipient_id)
        if topic:
            conditions.append("topic = ?")
            params.append(topic)
        if msg_type:
            conditions.append("msg_type = ?")
            params.append(msg_type)
        if time_start:
            conditions.append("created_at >= ?")
            params.append(time_start)
        if time_end:
            conditions.append("created_at <= ?")
            params.append(time_end)
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        return await self._db.execute_fetchall(
            f"SELECT * FROM messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
