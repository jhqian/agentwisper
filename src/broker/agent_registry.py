# Licensed under the Apache License, Version 2.0

"""Agent registry providing business logic over the agent persistence layer."""

from __future__ import annotations

import re
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

    async def _resolve_unique_name(self, name: str) -> str:
        """Resolve a unique agent name, appending -N suffix on collision."""
        existing = await self._agent_store.find_names_by_prefix(name)
        if name not in existing:
            return name
        pattern = re.compile(rf"^{re.escape(name)}-(\d+)$")
        max_suffix = 0
        for n in existing:
            m = pattern.match(n)
            if m:
                max_suffix = max(max_suffix, int(m.group(1)))
        return f"{name}-{max_suffix + 1}"

    async def register(
        self,
        name: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
        session_name: str | None = None,
    ) -> dict[str, str]:
        """Register a new agent. Returns agent_id and assigned_name."""
        assigned_name = await self._resolve_unique_name(name)
        agent_id = await self._agent_store.create(
            assigned_name, capabilities, metadata, session_name=session_name
        )
        return {"agent_id": agent_id, "assigned_name": assigned_name}

    async def deregister(self, agent_id: str) -> None:
        """Soft-delete: set status to disconnected, preserve all relationships."""
        agent = await self._agent_store.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        await self._agent_store.update_status(agent_id, AgentStatus.DISCONNECTED)
        await self._agent_store.update_session_name(agent_id, None)

    async def reconnect(self, name: str, session_name: str | None = None) -> dict[str, Any]:
        """Reconnect a disconnected agent by name.

        Restores agent to active status with same agent_id.
        Returns agent_id, assigned_name, status, and buffered_count.
        """
        agent = await self._agent_store.get_disconnected_by_name(name)
        if agent is None:
            raise ValueError(f"No disconnected agent with name '{name}' found")
        agent_id = agent["agent_id"]
        await self._agent_store.update_status(agent_id, AgentStatus.ACTIVE)
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

    async def pause(self, agent_id: str) -> None:
        """Pause an active agent.

        Only agents in 'active' status can be paused.
        Raises ValueError if agent not found or not active.
        """
        agent = await self._agent_store.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        if agent["status"] != AgentStatus.ACTIVE:
            raise ValueError(
                f"Cannot pause agent in status '{agent['status']}'"
            )
        await self._agent_store.update_status(agent_id, AgentStatus.PAUSED)

    async def resume(self, agent_id: str) -> dict[str, Any]:
        """Resume a paused agent.

        Only agents in 'paused' status can be resumed.
        Returns dict with new status and count of buffered (pending) messages.
        """
        agent = await self._agent_store.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        if agent["status"] != AgentStatus.PAUSED:
            raise ValueError(
                f"Cannot resume agent in status '{agent['status']}'"
            )
        await self._agent_store.update_status(agent_id, AgentStatus.ACTIVE)
        buffered = await self._message_store.get_pending_for_agent(agent_id)
        return {"status": "active", "buffered_count": len(buffered)}

    async def resolve_recipient(self, name_or_id: str) -> str | None:
        """Resolve a recipient identifier to an agent_id.

        Tries exact agent_id match first, then falls back to name lookup.
        Returns None if no match found or agent is disconnected.
        """
        agent = await self._agent_store.get(name_or_id)
        if agent is not None:
            if agent["status"] == AgentStatus.DISCONNECTED:
                return None
            return agent["agent_id"]
        agent = await self._agent_store.get_by_name(name_or_id)
        if agent is not None:
            if agent["status"] == AgentStatus.DISCONNECTED:
                return None
            return agent["agent_id"]
        return None

    async def list_agents(
        self, squad_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List all agents, optionally filtered by squad."""
        if squad_id:
            return await self._agent_store.list_by_squad(squad_id)
        return await self._agent_store.list_all()

    async def cleanup_expired(self, ttl_days: int) -> int:
        """Delegate to AgentStore cleanup."""
        return await self._agent_store.cleanup_expired_agents(ttl_days)
