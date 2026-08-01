# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Message router orchestrating P2P, RPC, and Pub/Sub message routing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agentwisper.common.types import MessageStatus, MessageType, SquadRole
from agentwisper.persistence.agent_store import AgentStore
from agentwisper.persistence.database import AsyncDatabase
from agentwisper.persistence.message_store import MessageStore
from agentwisper.persistence.squad_store import SquadStore
from agentwisper.persistence.subscription_store import SubscriptionStore


class MessageRouter:
    """Orchestrates message routing for P2P, RPC, and Pub/Sub patterns.

    Coordinates MessageStore, SubscriptionStore, AgentStore, and SquadStore
    to route messages between agents with permission enforcement.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db
        self._message_store = MessageStore(db)
        self._agent_store = AgentStore(db)
        self._subscription_store = SubscriptionStore(db)
        self._squad_store = SquadStore(db)

    async def _resolve_recipient(self, recipient: str) -> str:
        """Resolve a recipient identifier (agent_id or name) to an agent_id.

        Tries agent_id lookup first, then falls back to name lookup.
        Messages to disconnected agents are buffered and delivered on reconnect.
        """
        agent = await self._agent_store.get(recipient)
        if agent is not None:
            return agent["agent_id"]
        agent = await self._agent_store.get_by_name(recipient)
        if agent is not None:
            return agent["agent_id"]
        raise ValueError(f"Recipient '{recipient}' not found")

    async def _check_send_permission(
        self, sender_id: str, squad_id: str | None
    ) -> None:
        """Check that sender is allowed to send in the given squad context.

        Observers are not allowed to send messages. Only enforced when
        squad_id is provided and the sender is a member of that squad.
        System messages bypass all permission checks.
        """
        if sender_id == "system":
            return
        if squad_id is None:
            return
        role = await self._squad_store.get_member_role(squad_id, sender_id)
        if role is not None and role == SquadRole.OBSERVER:
            raise PermissionError(
                f"Agent {sender_id} is an observer in squad {squad_id} "
                f"and cannot send messages"
            )

    async def send_message(
        self,
        sender_id: str,
        recipient: str,
        payload: str,
        msg_type: MessageType,
        squad_id: str | None = None,
        msg_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a P2P or RPC request message.

        Resolves recipient by agent_id or name, persists the message,
        and returns msg_id with status.

        Args:
            sender_id: ID of the sending agent.
            recipient: agent_id or name of the receiving agent.
            payload: Message payload as string.
            msg_type: One of P2P or RPC_REQUEST.
            squad_id: Optional squad context for permission checks.
            msg_id: Optional client-provided msg_id. Auto-generated if None.

        Returns:
            Dict with msg_id and status.

        Raises:
            ValueError: If recipient cannot be resolved.
            PermissionError: If sender is an observer in the squad.
        """
        await self._check_send_permission(sender_id, squad_id)
        recipient_id = await self._resolve_recipient(recipient)
        msg_id = await self._message_store.create(
            sender_id=sender_id,
            recipient_id=recipient_id,
            msg_type=msg_type,
            payload=payload,
            squad_id=squad_id,
            msg_id=msg_id,
        )
        return {"msg_id": msg_id, "status": "pending", "recipient_id": recipient_id}

    async def broadcast_message(
        self,
        sender_id: str,
        topic: str,
        payload: str,
        squad_id: str | None = None,
        msg_id: str | None = None,
    ) -> dict[str, Any]:
        """Broadcast a Pub/Sub message to all subscribers of a topic.

        Persists the message with no direct recipient, looks up subscribers,
        and creates delivery logs for each subscriber.

        Args:
            sender_id: ID of the publishing agent.
            topic: Topic string to broadcast to.
            payload: Message payload as string.
            squad_id: Optional squad context for scoping and permissions.
            msg_id: Optional client-provided msg_id. Auto-generated if None.

        Returns:
            Dict with msg_id and subscriber_count.

        Raises:
            PermissionError: If sender is an observer in the squad.
        """
        await self._check_send_permission(sender_id, squad_id)

        msg_id = await self._message_store.create(
            sender_id=sender_id,
            recipient_id=None,
            msg_type=MessageType.PUBSUB,
            payload=payload,
            topic=topic,
            squad_id=squad_id,
            msg_id=msg_id,
        )

        # Get squad-scoped subscribers, then add global subscribers
        subscriber_ids: list[str] = []
        if squad_id is not None:
            squad_subs = await self._subscription_store.get_subscribers(
                topic, squad_id=squad_id
            )
            global_subs = await self._subscription_store.get_subscribers(topic)
            # Merge: squad-scoped + global, deduplicate
            seen: set[str] = set(subscriber_ids)
            for sid in squad_subs:
                if sid not in seen:
                    subscriber_ids.append(sid)
                    seen.add(sid)
            for sid in global_subs:
                if sid not in seen:
                    subscriber_ids.append(sid)
                    seen.add(sid)
        else:
            subscriber_ids = await self._subscription_store.get_subscribers(topic)

        if subscriber_ids:
            await self._message_store.create_delivery_logs(msg_id, subscriber_ids)

        return {
            "msg_id": msg_id,
            "subscriber_count": len(subscriber_ids),
            "subscriber_ids": subscriber_ids,
        }

    async def poll_messages(
        self,
        agent_id: str,
        limit: int = 50,
        unread_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Poll pending messages and delivery logs for an agent.

        Retrieves both direct messages (from messages table) and delivery
        log entries (from delivery_logs joined with messages), then marks
        all as delivered.

        Args:
            agent_id: ID of the polling agent.
            limit: Maximum number of each type to retrieve.
            unread_only: If True, only return pending/unread messages.

        Returns:
            Combined list of message dicts.
        """
        # unread_only=False is a pure query: return every message for the
        # agent (any status) without marking anything.
        if not unread_only:
            direct_messages = await self._message_store.get_all_for_agent(
                agent_id, limit=limit
            )
            delivery_messages = await self._message_store.get_all_deliveries(
                agent_id, limit=limit
            )
            combined = list(direct_messages)
            combined.extend(delivery_messages)
            return combined

        # Get pending direct messages
        direct_messages = await self._message_store.get_pending_for_agent(
            agent_id, limit=limit
        )

        # Get pending delivery logs (joined with message data)
        delivery_messages = await self._message_store.get_pending_deliveries(
            agent_id, limit=limit
        )

        # Mark all direct messages as delivered and acknowledged (batched)
        if direct_messages:
            direct_ids = [msg["msg_id"] for msg in direct_messages]
            now_iso = datetime.now(timezone.utc).isoformat()
            ph = ",".join("?" * len(direct_ids))
            await self._db.execute(
                f"UPDATE messages SET status = ?, delivered_at = ? "
                f"WHERE msg_id IN ({ph})",
                (MessageStatus.DELIVERED, now_iso, *direct_ids),
            )
            await self._db.execute(
                f"UPDATE messages SET status = ? "
                f"WHERE msg_id IN ({ph})",
                (MessageStatus.ACKNOWLEDGED, *direct_ids),
            )

        # Mark all delivery logs as delivered and acknowledged (batched)
        if delivery_messages:
            delivery_ids = [dlv["delivery_id"] for dlv in delivery_messages]
            now_iso = datetime.now(timezone.utc).isoformat()
            ph = ",".join("?" * len(delivery_ids))
            await self._db.execute(
                f"UPDATE delivery_logs SET status = ?, delivered_at = ? "
                f"WHERE delivery_id IN ({ph})",
                (MessageStatus.DELIVERED, now_iso, *delivery_ids),
            )
            await self._db.execute(
                f"UPDATE delivery_logs SET status = ? "
                f"WHERE delivery_id IN ({ph})",
                (MessageStatus.ACKNOWLEDGED, *delivery_ids),
            )

        # Combine results: direct messages first, then delivery log entries
        combined: list[dict[str, Any]] = []
        combined.extend(direct_messages)
        combined.extend(delivery_messages)

        return combined

    async def count_pending_messages(self) -> int:
        """Count all pending messages across all agents."""
        return await self._message_store.count_pending()
