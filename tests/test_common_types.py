from common.types import (
    AgentRecord, AgentStatus, MessageRecord, MessageType, MessageStatus,
    SquadRecord, SquadMembership, SquadRole, TeamRecord, TeamMembership,
    SubscriptionRecord, DeliveryLog
)


def test_agent_record_creation():
    agent = AgentRecord(
        agent_id="agent_0192test",
        name="test-agent",
        status=AgentStatus.ACTIVE,
        capabilities=["code", "review"],
        squad_id=None,
        current_team_id=None,
        created_at="2026-05-09T10:00:00Z",
        last_heartbeat="2026-05-09T10:00:00Z",
        metadata={}
    )
    assert agent.agent_id == "agent_0192test"
    assert agent.name == "test-agent"
    assert agent.status == AgentStatus.ACTIVE
    assert agent.capabilities == ["code", "review"]
    assert agent.squad_id is None


def test_agent_status_values():
    assert AgentStatus.ACTIVE == "active"
    assert AgentStatus.DISCONNECTED == "disconnected"


def test_message_record_creation():
    msg = MessageRecord(
        msg_id="msg_0192test",
        sender_id="agent_a",
        recipient_id="agent_b",
        topic=None,
        msg_type=MessageType.P2P,
        squad_id=None,
        payload='{"text": "hello"}',
        status=MessageStatus.PENDING,
        parent_msg_id=None,
        created_at="2026-05-09T10:00:00Z",
        delivered_at=None,
        expires_at=None
    )
    assert msg.msg_type == "p2p"
    assert msg.sender_id == "agent_a"
    assert msg.recipient_id == "agent_b"


def test_message_type_values():
    assert MessageType.P2P == "p2p"
    assert MessageType.RPC_REQUEST == "rpc_request"
    assert MessageType.RPC_RESPONSE == "rpc_response"
    assert MessageType.PUBSUB == "pubsub"


def test_squad_record_creation():
    squad = SquadRecord(
        squad_id="squad_0192test",
        name="test-squad",
        status="active",
        created_at="2026-05-09T10:00:00Z",
        dissolved_at=None,
        metadata={}
    )
    assert squad.squad_id == "squad_0192test"


def test_squad_membership_creation():
    membership = SquadMembership(
        squad_id="squad_0192test",
        agent_id="agent_0192test",
        joined_at="2026-05-09T10:00:00Z",
        role=SquadRole.LEADER
    )
    assert membership.role == "leader"


def test_team_record_creation():
    team = TeamRecord(
        team_id="team_0192test",
        topic="debug-session",
        initiator_id="agent_a",
        status="active",
        ttl_seconds=3600,
        created_at="2026-05-09T10:00:00Z",
        expires_at="2026-05-09T11:00:00Z",
        dismissed_at=None
    )
    assert team.ttl_seconds == 3600


def test_team_membership_creation():
    tm = TeamMembership(
        team_id="team_0192test",
        agent_id="agent_a",
        joined_at="2026-05-09T10:00:00Z"
    )
    assert tm.team_id == "team_0192test"


def test_subscription_record_creation():
    sub = SubscriptionRecord(
        sub_id="sub_0192test",
        agent_id="agent_a",
        topic="alerts",
        squad_id="squad_0192test",
        created_at="2026-05-09T10:00:00Z"
    )
    assert sub.topic == "alerts"


def test_delivery_log_creation():
    log = DeliveryLog(
        delivery_id="dlv_0192test",
        msg_id="msg_0192test",
        recipient_id="agent_b",
        status=MessageStatus.PENDING,
        delivered_at=None
    )
    assert log.delivery_id == "dlv_0192test"
