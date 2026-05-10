# Licensed under the Apache License, Version 2.0

"""Agent registry providing business logic over the agent persistence layer."""

from __future__ import annotations

from datetime import datetime, timezone
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

    async def register(
        self,
        name: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Register a new agent. Returns the generated agent_id."""
        return await self._agent_store.create(name, capabilities, metadata)

    async def deregister(self, agent_id: str) -> None:
        """Remove an agent from the registry.

        Raises ValueError if the agent does not exist.
        """
        agent = await self._agent_store.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        await self._agent_store.delete(agent_id)

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

    async def disconnect(self, agent_id: str) -> None:
        """Mark an agent as disconnected (heartbeat timeout)."""
        await self._agent_store.update_status(
            agent_id, AgentStatus.DISCONNECTED
        )

    async def reconnect(self, agent_id: str) -> None:
        """Reconnect a disconnected agent back to active."""
        await self._agent_store.update_status(agent_id, AgentStatus.ACTIVE)

    async def heartbeat(self, agent_id: str) -> None:
        """Update agent heartbeat timestamp to current UTC time."""
        now = datetime.now(timezone.utc).isoformat()
        await self._agent_store.update_heartbeat(agent_id, now)

    async def resolve_recipient(self, name_or_id: str) -> str | None:
        """Resolve a recipient identifier to an agent_id.

        Tries exact agent_id match first, then falls back to name lookup.
        Returns None if no match found.
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
