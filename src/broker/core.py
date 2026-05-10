# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Broker core orchestrator wiring all components together."""

from __future__ import annotations

from typing import Any

from common.config import BrokerConfig
from common.types import MessageType
from persistence.database import AsyncDatabase
from persistence.subscription_store import SubscriptionStore
from broker.agent_registry import AgentRegistry
from broker.heartbeat import HeartbeatMonitor
from broker.router import MessageRouter
from broker.squad_manager import SquadManager
from broker.team_manager import TeamManager


class Broker:
    """Top-level orchestrator that holds all components and provides a
    unified API for the MCP Server layer.

    Delegates each operation to the appropriate manager while managing
    the shared database connection and heartbeat monitor lifecycle.
    """

    def __init__(self, config: BrokerConfig) -> None:
        self._config = config
        self._db = AsyncDatabase(config.db_path)
        self._registry = AgentRegistry(self._db)
        self._squad_mgr = SquadManager(self._db)
        self._team_mgr = TeamManager(self._db)
        self._router = MessageRouter(self._db)
        self._heartbeat = HeartbeatMonitor(
            self._db, config.heartbeat_interval, config.heartbeat_timeout
        )
        self._sub_store = SubscriptionStore(self._db)
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize database and start background services."""
        if self._started:
            return
        await self._db.initialize()
        await self._heartbeat.start()
        self._started = True

    async def stop(self) -> None:
        """Stop background services and close database."""
        if not self._started:
            return
        await self._heartbeat.stop()
        await self._db.close()
        self._started = False

    # ------------------------------------------------------------------
    # Agent operations  (delegates to AgentRegistry)
    # ------------------------------------------------------------------

    async def register_agent(
        self,
        name: str,
        capabilities: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        agent_id = await self._registry.register(name, capabilities, metadata)
        return {"agent_id": agent_id, "status": "active"}

    async def deregister_agent(self, agent_id: str) -> dict:
        await self._registry.deregister(agent_id)
        return {"status": "deregistered"}

    async def pause_agent(self, agent_id: str) -> dict:
        await self._registry.pause(agent_id)
        return {"status": "paused"}

    async def resume_agent(self, agent_id: str) -> dict:
        return await self._registry.resume(agent_id)

    async def agent_heartbeat(self, agent_id: str) -> dict:
        await self._registry.heartbeat(agent_id)
        info = await self._registry.get_info(agent_id)
        return {"last_heartbeat": info["last_heartbeat"], "status": info["status"]}

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
    ) -> dict:
        return await self._router.send_message(
            sender_id, recipient, payload, MessageType(msg_type), squad_id
        )

    async def broadcast_message(
        self,
        sender_id: str,
        topic: str,
        payload: str,
        squad_id: str | None = None,
    ) -> dict:
        return await self._router.broadcast_message(
            sender_id, topic, payload, squad_id
        )

    async def reply_message(
        self, parent_msg_id: str, sender_id: str, payload: str
    ) -> dict:
        return await self._router.reply_message(parent_msg_id, sender_id, payload)

    async def poll_messages(
        self, agent_id: str, limit: int = 50, unread_only: bool = True
    ) -> dict:
        messages = await self._router.poll_messages(agent_id, limit, unread_only)
        return {"messages": messages}

    async def acknowledge_message(self, msg_id: str) -> dict:
        await self._router.acknowledge_message(msg_id)
        return {"status": "acknowledged"}

    async def acknowledge_delivery(self, delivery_id: str) -> dict:
        await self._router.acknowledge_delivery(delivery_id)
        return {"status": "acknowledged"}

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
        return {
            "status": "healthy" if self._started else "stopped",
            "active_agents": len(agents),
        }
