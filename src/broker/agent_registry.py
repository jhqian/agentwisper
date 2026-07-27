# Licensed under the Apache License, Version 2.0

"""Agent registry providing business logic over the agent persistence layer."""

from __future__ import annotations

import sqlite3
from typing import Any

from persistence.database import AsyncDatabase
from persistence.agent_store import AgentStore
from persistence.message_store import MessageStore
from common.types import AgentStatus


class AgentRegistry:
    """Business logic layer for agent lifecycle management.

    Wraps AgentStore and MessageStore to enforce state machine transitions,
    name resolution, and buffered message handling.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        self._agent_store = AgentStore(db)
        self._message_store = MessageStore(db)
        self._db = db

    async def _check_name_available(self, name: str) -> None:
        """Raise ValueError if the name is already taken by any agent."""
        existing = await self._agent_store.get_by_name(name)
        if existing is not None:
            raise ValueError(
                f"Name '{name}' is already registered. Use agent_reconnect to resume "
                f"an existing agent, or register with force=True to create a new agent "
                f"with the same name."
            )

    async def _hard_delete_agent(self, agent_id: str) -> None:
        """Delete an agent and all associated data."""
        await self._db.execute(
            "DELETE FROM delivery_logs WHERE recipient_id = ?", (agent_id,)
        )
        await self._db.execute(
            "DELETE FROM subscriptions WHERE agent_id = ?", (agent_id,)
        )
        await self._db.execute(
            "DELETE FROM squad_memberships WHERE agent_id = ?", (agent_id,)
        )
        await self._db.execute(
            "DELETE FROM team_memberships WHERE agent_id = ?", (agent_id,)
        )
        await self._db.execute(
            "DELETE FROM messages WHERE sender_id = ? OR recipient_id = ?",
            (agent_id, agent_id),
        )
        await self._db.execute(
            "DELETE FROM agents WHERE agent_id = ?", (agent_id,)
        )

    async def register(
        self,
        name: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
        session_name: str | None = None,
        force: bool = False,
    ) -> dict[str, str]:
        """Register a new agent. Returns agent_id and assigned_name.

        By default, rejects names that are already registered.
        Set force=True to delete any existing agent with the same name
        before creating a new registration.
        """
        if force:
            existing = await self._agent_store.get_by_name(name)
            if existing is not None:
                await self._hard_delete_agent(existing["agent_id"])
        else:
            await self._check_name_available(name)
        try:
            agent_id = await self._agent_store.create(
                name, capabilities, metadata, session_name=session_name
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Name '{name}' is already registered (concurrent registration). "
                f"Use agent_reconnect or register with force=True."
            ) from exc
        return {"agent_id": agent_id, "assigned_name": name}

    async def deregister(self, agent_id: str) -> None:
        """Soft-delete: set status to disconnected, preserve all relationships."""
        agent = await self._agent_store.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        await self._agent_store.update_status(agent_id, AgentStatus.DISCONNECTED)
        await self._agent_store.update_session_name(agent_id, None)

    async def reconnect(
        self,
        name: str,
        agent_id: str | None = None,
        session_name: str | None = None,
    ) -> dict[str, Any]:
        """Reconnect an agent with optional credential verification.

        When agent_id is provided, verifies name + agent_id match before
        force-takeover. When agent_id is None, falls back to name-only lookup
        (legacy path).
        """
        if agent_id is not None:
            agent = await self._agent_store.get(agent_id)
            if agent is None:
                raise ValueError(
                    f"Agent '{agent_id}' not found. Your previous identity may have "
                    f"expired. Use /agentsquad:register to create a new identity."
                )
            if agent["name"] != name:
                raise ValueError(
                    f"Credential mismatch: name '{name}' does not match agent_id "
                    f"'{agent_id}'. The agent is registered as '{agent['name']}'."
                )
            rows = await self._agent_store.update_status_and_session(
                agent_id, name, AgentStatus.ACTIVE, session_name
            )
            if rows == 0:
                raise ValueError(
                    f"Credential mismatch for agent_id '{agent_id}' and name '{name}'."
                )
            buffered = await self._message_store.get_pending_for_agent(agent_id)
            return {
                "agent_id": agent_id,
                "assigned_name": name,
                "status": "active",
                "buffered_count": len(buffered),
            }
        # Legacy name-only reconnect
        agent = await self._agent_store.get_by_name(name)
        if agent is None:
            raise ValueError(
                f"Agent named '{name}' not found. It may have never been registered "
                f"or may have expired after the retention period."
            )
        agent_id = agent["agent_id"]
        await self._agent_store.update_status(agent_id, AgentStatus.ACTIVE)
        await self._agent_store.update_last_seen(agent_id)
        if session_name:
            await self._agent_store.update_session_name(agent_id, session_name)
        buffered = await self._message_store.get_pending_for_agent(agent_id)
        return {
            "agent_id": agent_id,
            "assigned_name": name,
            "status": "active",
            "buffered_count": len(buffered),
        }

    async def get_info(self, agent_id: str) -> dict[str, Any] | None:
        """Retrieve agent information by ID."""
        return await self._agent_store.get(agent_id)

    async def resolve_recipient(self, name_or_id: str) -> str | None:
        """Resolve a recipient identifier to an agent_id.

        Tries exact agent_id match first, then falls back to name lookup.
        Returns None if no match found. Connected status is not checked --
        messages to disconnected agents are buffered for later delivery.
        """
        agent = await self._agent_store.get(name_or_id)
        if agent is not None:
            return agent["agent_id"]
        agent = await self._agent_store.get_by_name(name_or_id)
        if agent is not None:
            return agent["agent_id"]
        return None

    async def list_agents(
        self, squad_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List all agents, optionally filtered by squad."""
        if squad_id:
            return await self._agent_store.list_by_squad(squad_id)
        return await self._agent_store.list_all()

    async def list_active(self) -> list[dict[str, Any]]:
        """List active agents ordered by creation time."""
        return await self._agent_store.list_active()

    async def cleanup_expired(self, ttl_days: int) -> int:
        """Delegate to AgentStore cleanup."""
        return await self._agent_store.cleanup_expired_agents(ttl_days)
