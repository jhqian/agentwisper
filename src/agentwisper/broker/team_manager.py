# Copyright 2026 agentwisper contributors
#
# Licensed under the Apache License, Version 2.0

"""Team manager enforcing peer-based permissions for ad-hoc team operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agentwisper.persistence.agent_store import AgentStore
from agentwisper.persistence.database import AsyncDatabase
from agentwisper.persistence.team_store import TeamStore


class TeamManager:
    """Wraps TeamStore and AgentStore to manage ad-hoc teams.

    Ad-hoc team rules:
        - No roles: all members are equal peers
        - Any agent can form a team by specifying target agent IDs
        - Optional TTL: auto-dissolve after expiry
        - Agent can be in at most ONE ad-hoc team at a time
        - Agent can participate in 1 Squad AND 1 Team simultaneously
    """

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._team_store = TeamStore(db)
        self._agent_store = AgentStore(db)

    async def form(
        self,
        initiator_id: str,
        agent_ids: list[str],
        topic: str | None = None,
        ttl_seconds: int | None = None,
    ) -> str:
        """Create a new ad-hoc team with all specified agents as peers.

        Validates that no agent is already in a team before creating.
        Sets current_team_id on all member agents.

        Returns the generated team_id.

        Raises:
            ValueError: if any agent is already in a team.
        """
        # Check that no agent is already in a team
        for agent_id in agent_ids:
            agent = await self._agent_store.get(agent_id)
            if agent is not None and agent.get("current_team_id") is not None:
                raise ValueError(
                    f"Agent {agent_id} is already in a team"
                )

        team_id = await self._team_store.create(
            initiator_id=initiator_id,
            agent_ids=agent_ids,
            topic=topic,
            ttl_seconds=ttl_seconds,
        )

        # Set current_team_id for all members
        for agent_id in agent_ids:
            await self._agent_store.set_team(agent_id, team_id)

        return team_id

    async def dismiss(self, team_id: str, caller_id: str) -> None:
        """Dismiss a team. Any member can dismiss.

        Marks the team as dismissed and clears current_team_id for all members.

        Raises:
            PermissionError: if caller is not a member of the team.
        """
        # Verify caller is a member
        members = await self._team_store.get_members(team_id)
        member_ids = {m["agent_id"] for m in members}
        if caller_id not in member_ids:
            raise PermissionError(
                f"Agent {caller_id} is not a member of team {team_id}"
            )

        # Clear current_team_id for all members
        for member in members:
            await self._agent_store.set_team(member["agent_id"], None)

        await self._team_store.dismiss(team_id)

    async def get_info(self, team_id: str) -> dict[str, Any]:
        """Return team details with member list.

        Returns dict with 'team' and 'members' keys.
        """
        team = await self._team_store.get(team_id)
        members = await self._team_store.get_members(team_id)
        return {"team": team, "members": members}

    async def list_teams(
        self, agent_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List active teams, optionally filtered by agent membership."""
        if agent_id is not None:
            return await self._team_store.list_by_agent(agent_id)
        return await self._team_store.list_active()

    async def expire_teams(self) -> int:
        """Mark expired teams and clear members' current_team_id.

        Returns the count of newly expired teams.
        """
        # Get agents in teams that are about to expire
        now_iso = datetime.now(timezone.utc).isoformat()
        expiring_agents = await self._db.execute_fetchall(
            "SELECT tm.agent_id FROM team_memberships tm "
            "JOIN teams t ON t.team_id = tm.team_id "
            "WHERE t.status = 'active' AND t.expires_at IS NOT NULL AND t.expires_at < ?",
            (now_iso,),
        )

        # Mark expired teams in store
        count = await self._team_store.expire_expired_teams()

        # Clear current_team_id for affected agents
        for row in expiring_agents:
            await self._agent_store.set_team(row["agent_id"], None)

        return count
