# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Broker core orchestrator wiring all components together."""

from __future__ import annotations

import anyio
import logging
from datetime import datetime, timezone
from typing import Any

from broker.agent_registry import AgentRegistry
from broker.router import MessageRouter
from broker.squad_manager import SquadManager
from broker.team_manager import TeamManager
from common.config import BrokerConfig
from common.types import MessageType
from persistence.database import AsyncDatabase
from persistence.subscription_store import SubscriptionStore

logger = logging.getLogger(__name__)


class Broker:
    """Top-level orchestrator that holds all components and provides a
    unified API for the MCP Server layer.

    Delegates each operation to the appropriate manager while managing
    the shared database connection lifecycle.
    """

    def __init__(self, config: BrokerConfig) -> None:
        self._config = config
        self._db = AsyncDatabase(config.db_path)
        self._registry = AgentRegistry(self._db)
        self._squad_mgr = SquadManager(self._db)
        self._team_mgr = TeamManager(self._db)
        self._router = MessageRouter(self._db)
        self._sub_store = SubscriptionStore(self._db)
        self._wait_events: dict[str, anyio.Event] = {}
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize database and start background services."""
        if self._started:
            return
        await self._db.initialize()
        await self._reset_active_agents_on_startup()
        self._started = True

    async def stop(self) -> None:
        """Stop background services and close database."""
        if not self._started:
            return
        await self._db.close()
        self._started = False

    async def _reset_active_agents_on_startup(self) -> None:
        """Mark all active agents as disconnected after broker restart.

        MCP connections are lost when the broker process exits. All agents
        must reconnect to resume operations. Already-disconnected agents
        are left unchanged.
        """
        now = datetime.now(timezone.utc).isoformat()
        affected = await self._db.execute_fetchall(
            "SELECT agent_id FROM agents WHERE status = 'active'"
        )
        if not affected:
            return
        await self._db.execute(
            "UPDATE agents SET status = 'disconnected', "
            "disconnected_at = ?, session_name = NULL "
            "WHERE status = 'active'",
            (now,),
        )
        logger.info(
            "Broker startup: reset %d agent(s) to disconnected", len(affected)
        )

    # ------------------------------------------------------------------
    # Notification dispatch
    # ------------------------------------------------------------------

    async def _notify_recipients(self, recipient_ids: list[str]) -> None:
        """Wake any waiting message_wait callers."""
        for agent_id in recipient_ids:
            try:
                event = self._wait_events.get(agent_id)
                if event is not None:
                    event.set()
            except Exception:
                logger.exception("Failed to notify agent %s", agent_id)

    def register_wait(self, agent_id: str) -> anyio.Event:
        """Register an anyio.Event for message_wait. Returns the event."""
        event = anyio.Event()
        self._wait_events[agent_id] = event
        return event

    def unregister_wait(self, agent_id: str) -> None:
        """Remove wait event after message_wait completes."""
        self._wait_events.pop(agent_id, None)

    # ------------------------------------------------------------------
    # Agent operations  (delegates to AgentRegistry)
    # ------------------------------------------------------------------

    async def register_agent(
        self,
        name: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
        session_name: str | None = None,
    ) -> dict:
        result = await self._registry.register(name, capabilities, metadata, session_name=session_name)
        logger.info(
            "Agent registered: %s (%s) capabilities=%s session=%s",
            result["assigned_name"], result["agent_id"], capabilities, session_name,
        )
        return {
            "agent_id": result["agent_id"],
            "assigned_name": result["assigned_name"],
            "status": "active",
        }

    async def deregister_agent(self, agent_id: str) -> dict:
        self.unregister_wait(agent_id)
        # If agent leads a squad, dissolve it before removing membership
        agent_info = await self._registry.get_info(agent_id)
        agent_name = agent_info.get("name", "?") if agent_info else "?"
        if agent_info and agent_info.get("squad_id"):
            squad_id = agent_info["squad_id"]
            role = await self._squad_mgr._squad_store.get_member_role(
                squad_id, agent_id
            )
            if role == "leader":
                # Clear squad_id for all members, then mark squad dissolved
                members = await self._squad_mgr._squad_store.get_members(squad_id)
                for member in members:
                    if member["agent_id"] != agent_id:
                        await self._db.execute(
                            "UPDATE agents SET squad_id = NULL WHERE agent_id = ?",
                            (member["agent_id"],),
                        )
                await self._squad_mgr._squad_store.dissolve(squad_id)
                logger.info("Squad %s dissolved (leader %s deregistered)", squad_id, agent_name)

        await self._registry.deregister(agent_id)
        # Release all resources associated with the agent
        await self._sub_store.delete_by_agent(agent_id)
        await self._db.execute(
            "DELETE FROM squad_memberships WHERE agent_id = ?", (agent_id,)
        )
        await self._db.execute(
            "DELETE FROM team_memberships WHERE agent_id = ?", (agent_id,)
        )
        await self._db.execute(
            "UPDATE agents SET squad_id = NULL, current_team_id = NULL "
            "WHERE agent_id = ?", (agent_id,)
        )
        logger.info("Agent deregistered: %s (%s)", agent_name, agent_id)
        return {"status": "disconnected"}

    async def reconnect_agent(self, name: str, session_name: str | None = None) -> dict:
        """Reconnect a disconnected agent by name."""
        result = await self._registry.reconnect(name, session_name=session_name)
        logger.info(
            "Agent reconnected: %s (%s) session=%s buffered=%d",
            name, result["agent_id"], session_name, result.get("buffered_count", 0),
        )
        return result

    async def get_agent_info(self, agent_id: str) -> dict | None:
        return await self._registry.get_info(agent_id)

    async def list_agents(self, squad_id: str | None = None) -> dict:
        agents = await self._registry.list_agents(squad_id)
        return {"agents": agents}

    # ------------------------------------------------------------------
    # Squad operations  (delegates to SquadManager)
    # ------------------------------------------------------------------

    async def create_squad(
        self,
        name: str,
        caller_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        squad_id = await self._squad_mgr.create(name, caller_id, metadata)
        return {"squad_id": squad_id, "role": "leader"}

    async def dissolve_squad(self, squad_id: str, caller_id: str) -> dict:
        await self._squad_mgr.dissolve(squad_id, caller_id)
        return {"status": "dissolved"}

    async def join_squad(
        self, squad_id: str, agent_id: str, role: str, caller_id: str
    ) -> dict:
        await self._squad_mgr.join(squad_id, agent_id, role, caller_id)
        return {"status": "joined", "squad_id": squad_id, "role": role}

    async def leave_squad(self, agent_id: str) -> dict:
        await self._squad_mgr.leave(agent_id)
        return {"status": "left"}

    async def kick_from_squad(
        self, squad_id: str, agent_id: str, caller_id: str
    ) -> dict:
        await self._squad_mgr.kick(squad_id, agent_id, caller_id)
        return {"status": "kicked"}

    async def set_squad_role(
        self, squad_id: str, agent_id: str, role: str, caller_id: str
    ) -> dict:
        await self._squad_mgr.set_role(squad_id, agent_id, role, caller_id)
        return {"status": "role_updated", "new_role": role}

    async def get_squad_info(self, squad_id: str) -> dict:
        return await self._squad_mgr.get_info(squad_id)

    async def list_squads(self) -> dict:
        squads = await self._squad_mgr.list_squads()
        return {"squads": squads}

    # ------------------------------------------------------------------
    # Team operations  (delegates to TeamManager)
    # ------------------------------------------------------------------

    async def form_team(
        self,
        initiator_id: str,
        agent_ids: list[str],
        topic: str | None = None,
        ttl_seconds: int | None = None,
    ) -> dict:
        team_id = await self._team_mgr.form(initiator_id, agent_ids, topic, ttl_seconds)
        return {"team_id": team_id}

    async def dismiss_team(self, team_id: str, caller_id: str) -> dict:
        await self._team_mgr.dismiss(team_id, caller_id)
        return {"status": "dismissed"}

    async def get_team_info(self, team_id: str) -> dict:
        return await self._team_mgr.get_info(team_id)

    async def list_teams(self, agent_id: str | None = None) -> dict:
        teams = await self._team_mgr.list_teams(agent_id)
        return {"teams": teams}

    # ------------------------------------------------------------------
    # Message operations  (delegates to MessageRouter)
    # ------------------------------------------------------------------

    async def send_message(
        self,
        sender_id: str,
        recipient: str,
        payload: str,
        msg_type: str = "p2p",
        squad_id: str | None = None,
        msg_id: str | None = None,
    ) -> dict:
        result = await self._router.send_message(
            sender_id, recipient, payload, MessageType(msg_type), squad_id,
            msg_id=msg_id,
        )
        recipient_id = result.get("recipient_id", recipient)
        await self._notify_recipients([recipient_id])
        logger.info(
            "Message sent: %s -> %s type=%s msg_id=%s payload=%.120s",
            sender_id, recipient_id, msg_type, result.get("msg_id"),
            payload,
        )
        return result

    async def broadcast_message(
        self,
        sender_id: str,
        topic: str,
        payload: str,
        squad_id: str | None = None,
        msg_id: str | None = None,
    ) -> dict:
        result = await self._router.broadcast_message(
            sender_id, topic, payload, squad_id, msg_id=msg_id,
        )
        subscriber_ids = result.get("subscriber_ids", [])
        if subscriber_ids:
            await self._notify_recipients(subscriber_ids)
        logger.info(
            "Broadcast: %s -> topic=%s subscribers=%d squad=%s msg_id=%s payload=%.120s",
            sender_id, topic, len(subscriber_ids), squad_id,
            result.get("msg_id"), payload,
        )
        return result

    async def poll_messages(
        self, agent_id: str, limit: int = 50, unread_only: bool = True
    ) -> dict:
        messages = await self._router.poll_messages(agent_id, limit, unread_only)
        if messages:
            logger.info(
                "Messages polled: agent=%s count=%d", agent_id, len(messages),
            )
        return {"messages": messages}

    # ------------------------------------------------------------------
    # Subscription operations  (delegates to SubscriptionStore)
    # ------------------------------------------------------------------

    async def subscribe_topic(
        self, agent_id: str, topic: str, squad_id: str | None = None
    ) -> dict:
        sub_id = await self._sub_store.create(agent_id, topic, squad_id)
        return {"sub_id": sub_id}

    async def unsubscribe_topic(self, sub_id: str) -> dict:
        await self._sub_store.delete(sub_id)
        return {"status": "unsubscribed"}

    # ------------------------------------------------------------------
    # System operations
    # ------------------------------------------------------------------

    async def broker_status(self) -> dict:
        agents = await self._registry.list_agents()
        pending = await self._router.count_pending_messages()
        return {
            "status": "healthy" if self._started else "stopped",
            "active_agents": len(agents),
            "pending_messages": pending,
            "waiting_agents": len(self._wait_events),
        }

    # ------------------------------------------------------------------
    # Maintenance operations
    # ------------------------------------------------------------------

    async def _run_cleanup(self, ttl_days: int | None = None) -> int:
        """Run one cleanup cycle. Returns count of removed agents."""
        if ttl_days is None:
            ttl_days = self._config.disconnected_ttl_days
        if ttl_days <= 0:
            return 0
        return await self._registry.cleanup_expired(ttl_days)
