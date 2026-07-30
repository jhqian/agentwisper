# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Squad manager enforcing role-based permissions for squad operations."""

from __future__ import annotations

from typing import Any

from agentsquad.common.types import SquadRole
from agentsquad.persistence.agent_store import AgentStore
from agentsquad.persistence.database import AsyncDatabase
from agentsquad.persistence.squad_store import SquadStore


class SquadManager:
    """Wraps SquadStore and AgentStore to enforce role-based permissions.

    Permission matrix:
        Action                  leader  member  observer
        Dissolve squad          Y       N       N
        Change member roles     Y       N       N
        Remove member (kick)    Y       N       N
        Invite agent to squad   Y       N       N
        Transfer leadership     Y       N       N
        Send messages           Y       Y       N
        Subscribe/poll/query    Y       Y       Y
        Leave squad             Y       Y       Y
    """

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._squad_store = SquadStore(db)
        self._agent_store = AgentStore(db)

    async def _require_leader(self, squad_id: str, caller_id: str) -> None:
        """Raise PermissionError if caller is not the leader of the squad."""
        role = await self._squad_store.get_member_role(squad_id, caller_id)
        if role != SquadRole.LEADER:
            raise PermissionError(
                f"Agent {caller_id} is not the leader of squad {squad_id}"
            )

    async def create(
        self,
        name: str,
        creator_agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new squad and add creator as leader.

        Returns the generated squad_id.
        """
        squad_id = await self._squad_store.create(name, metadata)
        await self._squad_store.add_member(squad_id, creator_agent_id, SquadRole.LEADER)
        await self._agent_store.set_squad(creator_agent_id, squad_id)
        return squad_id

    async def dissolve(self, squad_id: str, caller_id: str) -> None:
        """Dissolve a squad. Leader only.

        Marks the squad as dissolved and clears squad_id for all members.
        """
        await self._require_leader(squad_id, caller_id)
        members = await self._squad_store.get_members(squad_id)
        for member in members:
            await self._agent_store.set_squad(member["agent_id"], None)
        await self._squad_store.dissolve(squad_id)

    async def join(
        self,
        squad_id: str,
        agent_id: str,
        role: SquadRole,
        caller_id: str,
    ) -> None:
        """Add an agent to a squad. Leader only.

        Sets the agent's squad_id in the agents table.
        """
        await self._require_leader(squad_id, caller_id)
        await self._squad_store.add_member(squad_id, agent_id, str(role))
        await self._agent_store.set_squad(agent_id, squad_id)

    async def leave(self, agent_id: str) -> None:
        """Remove self from squad. Any member can leave.

        Clears the agent's squad_id in the agents table.
        """
        agent = await self._agent_store.get(agent_id)
        if agent is None or agent["squad_id"] is None:
            return
        squad_id = agent["squad_id"]
        await self._squad_store.remove_member(squad_id, agent_id)
        await self._agent_store.set_squad(agent_id, None)

    async def kick(self, squad_id: str, agent_id: str, caller_id: str) -> None:
        """Remove a member from the squad. Leader only.

        Clears the kicked agent's squad_id.
        """
        await self._require_leader(squad_id, caller_id)
        await self._squad_store.remove_member(squad_id, agent_id)
        await self._agent_store.set_squad(agent_id, None)

    async def set_role(
        self,
        squad_id: str,
        agent_id: str,
        new_role: SquadRole,
        caller_id: str,
    ) -> None:
        """Change a member's role. Leader only.

        If new_role is LEADER, the current leader is demoted to MEMBER.
        """
        await self._require_leader(squad_id, caller_id)
        if new_role == SquadRole.LEADER:
            # Demote current leader to member
            await self._squad_store.set_member_role(squad_id, caller_id, SquadRole.MEMBER)
        await self._squad_store.set_member_role(squad_id, agent_id, str(new_role))

    async def get_info(self, squad_id: str) -> dict[str, Any]:
        """Return squad details with member list.

        Returns dict with 'squad' and 'members' keys.
        """
        squad = await self._squad_store.get(squad_id)
        members = await self._squad_store.get_members(squad_id)
        return {"squad": squad, "members": members}

    async def list_squads(self) -> list[dict[str, Any]]:
        """List all active squads."""
        return await self._squad_store.list_active()

    async def check_permission(
        self, agent_id: str, squad_id: str, action: str
    ) -> bool:
        """Check if an agent can perform a given action in a squad.

        Actions:
            - 'dissolve', 'change_role', 'kick', 'invite', 'transfer': leader only
            - 'send_message': leader or member
            - 'subscribe', 'poll', 'query': any member (leader, member, observer)
            - 'leave': any member
        """
        role = await self._squad_store.get_member_role(squad_id, agent_id)
        if role is None:
            return False

        leader_only = {"dissolve", "change_role", "kick", "invite", "transfer"}
        leader_or_member = {"send_message", "leave"}
        any_member = {"subscribe", "poll", "query"}

        if action in leader_only:
            return role == SquadRole.LEADER
        if action in leader_or_member:
            return role in (SquadRole.LEADER, SquadRole.MEMBER)
        if action in any_member:
            return role in (SquadRole.LEADER, SquadRole.MEMBER, SquadRole.OBSERVER)
        return False
