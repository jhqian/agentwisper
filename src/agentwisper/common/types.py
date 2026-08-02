from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentStatus(StrEnum):
    ACTIVE = "active"
    DISCONNECTED = "disconnected"


class MessageType(StrEnum):
    P2P = "p2p"
    RPC_REQUEST = "rpc_request"
    RPC_RESPONSE = "rpc_response"
    PUBSUB = "pubsub"
    NOTIFICATION = "notification"
    COORDINATION = "coordination"


class MessageStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"


class SquadRole(StrEnum):
    LEADER = "leader"
    MEMBER = "member"
    OBSERVER = "observer"


@dataclass
class AgentRecord:
    agent_id: str
    name: str
    status: AgentStatus
    squad_id: str | None
    current_team_id: str | None
    created_at: str
    last_seen: str
    session_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageRecord:
    msg_id: str
    sender_id: str
    recipient_id: str | None
    topic: str | None
    msg_type: MessageType
    squad_id: str | None
    payload: str
    status: MessageStatus
    parent_msg_id: str | None
    created_at: str
    delivered_at: str | None
    expires_at: str | None


@dataclass
class DeliveryLog:
    delivery_id: str
    msg_id: str
    recipient_id: str
    status: MessageStatus
    delivered_at: str | None


@dataclass
class SquadRecord:
    squad_id: str
    name: str
    status: str
    created_at: str
    dissolved_at: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SquadMembership:
    squad_id: str
    agent_id: str
    joined_at: str
    role: SquadRole


@dataclass
class TeamRecord:
    team_id: str
    topic: str | None
    initiator_id: str
    status: str
    ttl_seconds: int | None
    created_at: str
    expires_at: str | None
    dismissed_at: str | None


@dataclass
class TeamMembership:
    team_id: str
    agent_id: str
    joined_at: str


@dataclass
class SubscriptionRecord:
    sub_id: str
    agent_id: str
    topic: str
    squad_id: str | None
    created_at: str
