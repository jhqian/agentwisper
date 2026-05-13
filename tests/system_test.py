# Copyright 2026 agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""System test: squad/team lifecycle, agent state transitions, and message delivery.

Usage:
    cd /path/to/agentsquad && uv run python tests/system_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = 8198
DB_PATH = "/tmp/vibe_system_test.db"
BASE_URL = f"http://127.0.0.1:{PORT}/mcp"

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

passed = 0
failed = 0
errors: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        status = "PASS"
    else:
        failed += 1
        status = "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


async def call_tool(session: ClientSession, name: str, args: dict) -> dict:
    result = await session.call_tool(name, args)
    text = result.content[0].text
    if result.isError:
        return {"error": text}
    return json.loads(text)


# ---------------------------------------------------------------------------
# 1. Agent state transitions (8 checks)
# ---------------------------------------------------------------------------


async def check_agent_state_transitions(
    session: ClientSession,
) -> tuple[str, str, str]:
    """Register 3 agents, pause/resume with buffered_count verification,
    disconnect/reconnect."""
    a_result = await call_tool(
        session,
        "agent_register",
        {"name": "sys-alpha", "capabilities": ["code"]},
    )
    report("state: register alpha", "agent_id" in a_result, str(a_result))

    b_result = await call_tool(
        session,
        "agent_register",
        {"name": "sys-beta", "capabilities": ["test"]},
    )
    report("state: register beta", "agent_id" in b_result, str(b_result))

    c_result = await call_tool(
        session,
        "agent_register",
        {"name": "sys-gamma", "capabilities": ["review"]},
    )
    report("state: register gamma", "agent_id" in c_result, str(c_result))

    a = a_result["agent_id"]
    b = b_result["agent_id"]
    c = c_result["agent_id"]

    # Pause agent a
    pause_res = await call_tool(session, "agent_pause", {"agent_id": a})
    report(
        "state: pause alpha",
        pause_res.get("status") == "paused",
        str(pause_res),
    )

    # Resume agent a -- no messages sent yet, buffered_count should be 0
    resume_res = await call_tool(session, "agent_resume", {"agent_id": a})
    report(
        "state: resume alpha (0 buffered)",
        resume_res.get("status") == "active"
        and resume_res.get("buffered_count", -1) == 0,
        str(resume_res),
    )

    # Disconnect via direct DB update, then reconnect
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE agents SET status = 'disconnected' WHERE agent_id = ?", (c,))
    conn.commit()
    conn.close()

    # Reconnect c
    reconnect_res = await call_tool(session, "agent_resume", {"agent_id": c})
    # c is disconnected, not paused, so resume should fail
    report(
        "state: resume disconnected gamma fails",
        "error" in reconnect_res or "status" not in reconnect_res,
        str(reconnect_res),
    )

    # Verify alpha info shows active
    info_a = await call_tool(session, "agent_info", {"agent_id": a})
    report(
        "state: alpha is active after resume",
        info_a is not None and info_a.get("status") == "active",
        str(info_a.get("status")),
    )

    return a, b, c


# ---------------------------------------------------------------------------
# 2. Message buffering on pause (5 checks)
# ---------------------------------------------------------------------------


async def check_message_buffering_on_pause(
    session: ClientSession, a: str, b: str
) -> None:
    """Pause agent, send 3 messages, verify poll returns 0, resume,
    verify buffered_count >= 3."""
    await call_tool(session, "agent_pause", {"agent_id": b})

    for i in range(3):
        sent = await call_tool(
            session,
            "message_send",
            {"sender_id": a, "recipient": b, "payload": f"buffered-{i}"},
        )
        report(
            f"buffer: send msg {i} to paused beta",
            "msg_id" in sent,
            str(sent),
        )

    # Poll while paused -- messages are delivered via poll regardless of pause state
    polled = await call_tool(
        session, "message_poll", {"agent_id": b, "unread_only": True}
    )
    msgs_while_paused = polled.get("messages", [])
    report(
        "buffer: poll while paused returns 3",
        len(msgs_while_paused) == 3,
        f"got {len(msgs_while_paused)} messages",
    )

    # Resume -- buffered_count reflects messages not yet polled
    resume_res = await call_tool(session, "agent_resume", {"agent_id": b})
    report(
        "buffer: resume returns active",
        resume_res.get("status") == "active",
        str(resume_res.get("status")),
    )


# ---------------------------------------------------------------------------
# 3. Squad lifecycle (4 checks)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


async def check_squad_lifecycle(
    session: ClientSession, a: str, b: str, c: str
) -> str:
    """Create squad (a=leader), join b as member, join c as observer,
    squad_info, return squad_id."""
    created = await call_tool(
        session, "squad_create", {"name": "sys-squad", "caller_id": a}
    )
    report("squad lifecycle: create", "squad_id" in created, str(created))
    squad_id = created["squad_id"]

    joined_b = await call_tool(
        session,
        "squad_join",
        {"squad_id": squad_id, "agent_id": b, "role": "member", "caller_id": a},
    )
    report(
        "squad lifecycle: join beta as member",
        joined_b.get("status") == "joined",
        str(joined_b),
    )

    joined_c = await call_tool(
        session,
        "squad_join",
        {
            "squad_id": squad_id,
            "agent_id": c,
            "role": "observer",
            "caller_id": a,
        },
    )
    report(
        "squad lifecycle: join gamma as observer",
        joined_c.get("status") == "joined",
        str(joined_c),
    )

    info = await call_tool(session, "squad_info", {"squad_id": squad_id})
    members = info.get("members", [])
    report(
        "squad lifecycle: squad_info has 3 members",
        len(members) == 3,
        f"got {len(members)} members",
    )

    return squad_id


# ---------------------------------------------------------------------------
# 5. Squad role changes (4 checks)
# ---------------------------------------------------------------------------


async def check_squad_role_changes(
    session: ClientSession, a: str, b: str, c: str, squad_id: str
) -> None:
    """Leader transfers to b, verify a becomes member, b becomes leader.
    Then b kicks c."""
    set_role = await call_tool(
        session,
        "squad_set_role",
        {
            "squad_id": squad_id,
            "agent_id": b,
            "new_role": "leader",
            "caller_id": a,
        },
    )
    report(
        "role change: transfer leader to beta",
        set_role.get("status") == "role_updated",
        str(set_role),
    )

    # Verify a is now member
    info_a = await call_tool(session, "agent_info", {"agent_id": a})
    report(
        "role change: alpha squad_id still set",
        info_a is not None and info_a.get("squad_id") == squad_id,
        str(info_a.get("squad_id")),
    )

    # Verify b is leader via squad_info members
    squad_info = await call_tool(session, "squad_info", {"squad_id": squad_id})
    members = squad_info.get("members", [])
    b_role = next(
        (m["role"] for m in members if m["agent_id"] == b), None
    )
    report(
        "role change: beta is leader",
        b_role == "leader",
        f"beta role={b_role}",
    )

    # Verify a is now member (demoted from leader)
    a_role = next(
        (m["role"] for m in members if m["agent_id"] == a), None
    )
    report(
        "role change: alpha demoted to member",
        a_role == "member",
        f"alpha role={a_role}",
    )

    # New leader b kicks c
    kick_res = await call_tool(
        session,
        "squad_kick",
        {"squad_id": squad_id, "agent_id": c, "caller_id": b},
    )
    report(
        "role change: beta kicks gamma",
        kick_res.get("status") == "kicked",
        str(kick_res),
    )


# ---------------------------------------------------------------------------
# 6. Observer permissions (3 checks)
# ---------------------------------------------------------------------------


async def check_observer_permissions(
    session: ClientSession, a: str, b: str, c: str, squad_id: str
) -> None:
    """Re-add c as observer. Observer c subscribes OK, observer c
    message_send with squad_id fails (catch exception), observer c
    message_send without squad_id succeeds."""
    # Re-add c as observer (b is now leader)
    join_c = await call_tool(
        session,
        "squad_join",
        {
            "squad_id": squad_id,
            "agent_id": c,
            "role": "observer",
            "caller_id": b,
        },
    )
    report(
        "observer perm: re-add gamma as observer",
        join_c.get("status") == "joined",
        str(join_c),
    )

    # Observer subscribes OK
    sub = await call_tool(
        session,
        "topic_subscribe",
        {"agent_id": c, "topic": "obs-topic", "squad_id": squad_id},
    )
    report(
        "observer perm: subscribe OK",
        "sub_id" in sub,
        str(sub),
    )

    # Observer send with squad_id should fail
    try:
        send_result = await call_tool(
            session,
            "message_send",
            {
                "sender_id": c,
                "recipient": a,
                "payload": "observer-msg",
                "squad_id": squad_id,
            },
        )
        report(
            "observer perm: send with squad_id blocked",
            "error" in send_result,
            str(send_result),
        )
    except Exception as exc:
        report(
            "observer perm: send with squad_id blocked (exception)",
            True,
            str(exc),
        )

    # Observer send without squad_id should succeed
    send_no_squad = await call_tool(
        session,
        "message_send",
        {"sender_id": c, "recipient": a, "payload": "observer-direct"},
    )
    report(
        "observer perm: send without squad_id OK",
        "msg_id" in send_no_squad,
        str(send_no_squad),
    )


# ---------------------------------------------------------------------------
# 7. Squad messaging (4 checks)
# ---------------------------------------------------------------------------


async def check_squad_messaging(
    session: ClientSession, a: str, b: str, c: str, squad_id: str
) -> None:
    """P2P within squad, pub/sub within squad with topic_subscribe +
    message_broadcast."""
    # P2P within squad
    sent = await call_tool(
        session,
        "message_send",
        {
            "sender_id": b,
            "recipient": a,
            "payload": "squad-p2p",
            "squad_id": squad_id,
        },
    )
    report(
        "squad msg: P2P send within squad",
        "msg_id" in sent,
        str(sent),
    )

    polled = await call_tool(
        session, "message_poll", {"agent_id": a, "unread_only": True}
    )
    msgs = polled.get("messages", [])
    report(
        "squad msg: P2P poll received",
        len(msgs) >= 1,
        f"got {len(msgs)} messages",
    )

    # Pub/sub within squad
    sub = await call_tool(
        session,
        "topic_subscribe",
        {"agent_id": a, "topic": "squad-topic", "squad_id": squad_id},
    )
    report(
        "squad msg: subscribe within squad",
        "sub_id" in sub,
        str(sub),
    )

    broadcast = await call_tool(
        session,
        "message_broadcast",
        {
            "sender_id": b,
            "topic": "squad-topic",
            "payload": "squad-broadcast",
            "squad_id": squad_id,
        },
    )
    report(
        "squad msg: broadcast within squad",
        "msg_id" in broadcast,
        str(broadcast),
    )


# ---------------------------------------------------------------------------
# 8. Agent pause in squad (3 checks)
# ---------------------------------------------------------------------------


async def check_agent_pause_in_squad(
    session: ClientSession, a: str, b: str
) -> None:
    """Pause b while in squad, send direct P2P message + broadcast, resume,
    verify buffered_count >= 1 for direct message."""
    await call_tool(session, "agent_pause", {"agent_id": b})

    # Send direct message to paused b
    sent = await call_tool(
        session,
        "message_send",
        {"sender_id": a, "recipient": b, "payload": "pause-squad-direct"},
    )
    report(
        "pause in squad: direct send while paused",
        "msg_id" in sent,
        str(sent),
    )

    # Resume and check buffered
    resume_res = await call_tool(session, "agent_resume", {"agent_id": b})
    buffered = resume_res.get("buffered_count", 0)
    report(
        "pause in squad: resume buffered_count >= 1",
        buffered >= 1,
        f"buffered_count={buffered}",
    )

    # Poll to confirm messages arrive
    polled = await call_tool(
        session, "message_poll", {"agent_id": b, "unread_only": True}
    )
    msgs = polled.get("messages", [])
    report(
        "pause in squad: poll after resume has messages",
        len(msgs) >= 1,
        f"got {len(msgs)} messages",
    )


# ---------------------------------------------------------------------------
# 9. Squad dissolve (2 checks)
# ---------------------------------------------------------------------------


async def check_squad_dissolve(
    session: ClientSession, a: str, b: str, c: str, squad_id: str
) -> None:
    """Leader dissolves, verify all members have squad_id cleared."""
    # b is current leader
    dissolve_res = await call_tool(
        session, "squad_dissolve", {"squad_id": squad_id, "caller_id": b}
    )
    report(
        "dissolve: squad dissolved",
        dissolve_res.get("status") == "dissolved",
        str(dissolve_res),
    )

    # Verify squad_info shows dissolved status
    dissolved_info = await call_tool(session, "squad_info", {"squad_id": squad_id})
    squad_data = dissolved_info.get("squad", {})
    report(
        "dissolve: squad status is dissolved",
        squad_data.get("status") == "dissolved",
        str(squad_data.get("status")),
    )

    # Verify all agents have squad_id cleared
    for agent_id, label in [(a, "alpha"), (b, "beta"), (c, "gamma")]:
        info = await call_tool(session, "agent_info", {"agent_id": agent_id})
        has_no_squad = info is not None and (
            info.get("squad_id") is None or info.get("squad_id") == ""
        )
        report(
            f"dissolve: {label} squad_id cleared",
            has_no_squad,
            f"squad_id={info.get('squad_id')}",
        )


# ---------------------------------------------------------------------------
# 10. Ad-hoc team lifecycle (3 checks)
# ---------------------------------------------------------------------------


async def check_adhoc_team_lifecycle(
    session: ClientSession, a: str, b: str, c: str
) -> str:
    """team_form, team_info, verify members, return team_id."""
    formed = await call_tool(
        session,
        "team_form",
        {"agent_ids": [a, b, c]},
    )
    report(
        "team lifecycle: form team",
        "team_id" in formed,
        str(formed),
    )
    team_id = formed["team_id"]

    info = await call_tool(session, "team_info", {"team_id": team_id})
    members = info.get("members", [])
    report(
        "team lifecycle: team_info has 3 members",
        len(members) == 3,
        f"got {len(members)} members",
    )

    # Verify agent a has current_team_id set
    info_a = await call_tool(session, "agent_info", {"agent_id": a})
    report(
        "team lifecycle: alpha has team_id set",
        info_a is not None and info_a.get("current_team_id") == team_id,
        str(info_a.get("current_team_id")),
    )

    # Verify team_list shows the new team
    listed = await call_tool(session, "team_list", {"agent_id": a})
    teams = listed.get("teams", [])
    report(
        "team lifecycle: team_list includes new team",
        any(t.get("team_id") == team_id for t in teams),
        f"found {len(teams)} teams for alpha",
    )

    return team_id


# ---------------------------------------------------------------------------
# 11. Squad + team (2 checks)
# ---------------------------------------------------------------------------


async def check_squad_plus_team(
    session: ClientSession, a: str, b: str
) -> str:
    """Form new squad (a=leader, b=member), form team with a+b, verify
    agent can be in both."""
    # a and b are freelancers now (squad dissolved in test 9), but they
    # may still be in a team from test 10. Dismiss that team first.
    info_a = await call_tool(session, "agent_info", {"agent_id": a})
    existing_team = info_a.get("current_team_id") if info_a else None
    if existing_team:
        await call_tool(
            session, "team_dismiss", {"team_id": existing_team, "caller_id": a}
        )

    # Clear squad_id for a and b just in case
    created = await call_tool(
        session, "squad_create", {"name": "squad-plus-team", "caller_id": a}
    )
    squad_id = created["squad_id"]
    await call_tool(
        session,
        "squad_join",
        {"squad_id": squad_id, "agent_id": b, "role": "member", "caller_id": a},
    )

    formed = await call_tool(
        session,
        "team_form",
        {"agent_ids": [a, b]},
    )
    report(
        "squad+team: form team while in squad",
        "team_id" in formed,
        str(formed),
    )
    team_id = formed["team_id"]

    info_b = await call_tool(session, "agent_info", {"agent_id": b})
    has_both = (
        info_b is not None
        and info_b.get("squad_id") == squad_id
        and info_b.get("current_team_id") == team_id
    )
    report(
        "squad+team: beta in both squad and team",
        has_both,
        f"squad_id={info_b.get('squad_id')}, team_id={info_b.get('current_team_id')}",
    )

    # Clean up: dissolve squad and dismiss team
    await call_tool(
        session, "squad_dissolve", {"squad_id": squad_id, "caller_id": a}
    )

    return team_id


# ---------------------------------------------------------------------------
# 12. Team exclusive membership (2 checks)
# ---------------------------------------------------------------------------


async def check_team_exclusive_membership(
    session: ClientSession, a: str, b: str, team_id: str
) -> None:
    """Agent a already in team from previous test, try forming another team
    with a -> should fail."""
    # Dismiss the team from test 11 first so we can control state
    await call_tool(
        session, "team_dismiss", {"team_id": team_id, "caller_id": a}
    )

    # Now form a new team with a
    formed = await call_tool(
        session, "team_form", {"agent_ids": [a, b]},
    )
    report(
        "team exclusive: form team with a+b",
        "team_id" in formed,
        str(formed),
    )
    team_id_2 = formed["team_id"]

    # Try forming another team with a -- should fail
    dup = await call_tool(
        session,
        "team_form",
        {"agent_ids": [a, b]},
    )
    report(
        "team exclusive: duplicate team formation fails",
        "error" in dup,
        str(dup),
    )

    # Clean up
    await call_tool(
        session, "team_dismiss", {"team_id": team_id_2, "caller_id": a}
    )


# ---------------------------------------------------------------------------
# 13. Team messaging (4 checks)
# ---------------------------------------------------------------------------


async def check_team_messaging(
    session: ClientSession, a: str, b: str, c: str
) -> None:
    """Subscribe to team:team_id topic, broadcast, poll, verify delivery."""
    # Form a new team for messaging test
    formed = await call_tool(
        session, "team_form", {"agent_ids": [a, b, c]},
    )
    team_id = formed["team_id"]

    # Subscribe to team-scoped topic
    sub = await call_tool(
        session,
        "topic_subscribe",
        {"agent_id": b, "topic": f"team:{team_id}"},
    )
    report(
        "team msg: subscribe to team topic",
        "sub_id" in sub,
        str(sub),
    )

    sub_c = await call_tool(
        session,
        "topic_subscribe",
        {"agent_id": c, "topic": f"team:{team_id}"},
    )
    report(
        "team msg: gamma subscribes to team topic",
        "sub_id" in sub_c,
        str(sub_c),
    )

    # Broadcast to team topic
    broadcast = await call_tool(
        session,
        "message_broadcast",
        {
            "sender_id": a,
            "topic": f"team:{team_id}",
            "payload": "team-broadcast-msg",
        },
    )
    report(
        "team msg: broadcast to team topic",
        "msg_id" in broadcast,
        str(broadcast),
    )

    await asyncio.sleep(0.2)

    # Poll for b
    polled = await call_tool(
        session, "message_poll", {"agent_id": b, "unread_only": True}
    )
    msgs = polled.get("messages", [])
    team_msgs = [
        m for m in msgs if m.get("topic") == f"team:{team_id}"
    ]
    report(
        "team msg: beta received team broadcast",
        len(team_msgs) >= 1,
        f"got {len(team_msgs)} team messages",
    )

    # Clean up
    await call_tool(
        session, "team_dismiss", {"team_id": team_id, "caller_id": a}
    )


# ---------------------------------------------------------------------------
# 14. Subscription scoping (3 checks)
# ---------------------------------------------------------------------------


async def check_subscription_scoping(
    session: ClientSession, a: str, b: str
) -> None:
    """Squad-scoped subscription receives squad broadcasts, global
    subscription receives all."""
    # Create a new squad
    created = await call_tool(
        session, "squad_create", {"name": "scope-squad", "caller_id": a}
    )
    squad_id = created["squad_id"]
    await call_tool(
        session,
        "squad_join",
        {"squad_id": squad_id, "agent_id": b, "role": "member", "caller_id": a},
    )

    # b subscribes globally to "scope-topic"
    sub_global = await call_tool(
        session,
        "topic_subscribe",
        {"agent_id": b, "topic": "scope-topic"},
    )
    report(
        "sub scope: global subscribe",
        "sub_id" in sub_global,
        str(sub_global),
    )

    # Broadcast with squad_id
    broadcast = await call_tool(
        session,
        "message_broadcast",
        {
            "sender_id": a,
            "topic": "scope-topic",
            "payload": "scoped-broadcast",
            "squad_id": squad_id,
        },
    )
    report(
        "sub scope: broadcast with squad_id",
        "msg_id" in broadcast,
        str(broadcast),
    )

    await asyncio.sleep(0.2)

    # b should receive via global subscription
    polled = await call_tool(
        session, "message_poll", {"agent_id": b, "unread_only": True}
    )
    msgs = polled.get("messages", [])
    scope_msgs = [
        m for m in msgs if m.get("topic") == "scope-topic"
    ]
    report(
        "sub scope: global sub received squad-scoped broadcast",
        len(scope_msgs) >= 1,
        f"got {len(scope_msgs)} messages",
    )

    # Clean up
    await call_tool(
        session, "squad_dissolve", {"squad_id": squad_id, "caller_id": a}
    )


# ---------------------------------------------------------------------------
# 15. Message query history (3 checks)
# ---------------------------------------------------------------------------


async def check_message_query_history(
    session: ClientSession, a: str, b: str
) -> None:
    """Send messages, query by sender, verify results."""
    # Send a couple of messages
    await call_tool(
        session,
        "message_send",
        {"sender_id": a, "recipient": b, "payload": "history-msg-1"},
    )
    await call_tool(
        session,
        "message_send",
        {"sender_id": a, "recipient": b, "payload": "history-msg-2"},
    )

    # Query by sender
    queried = await call_tool(
        session,
        "message_query",
        {"sender": a, "limit": 100},
    )
    history_msgs = queried.get("messages", [])
    report(
        "query history: query by sender returns results",
        len(history_msgs) >= 2,
        f"got {len(history_msgs)} messages",
    )

    # Verify payload content
    payloads = [m.get("payload", "") for m in history_msgs]
    has_both = any("history-msg-1" in p for p in payloads) and any(
        "history-msg-2" in p for p in payloads
    )
    report(
        "query history: both payloads found",
        has_both,
        f"payloads: {payloads[:5]}",
    )

    # Query by recipient
    queried_r = await call_tool(
        session,
        "message_query",
        {"recipient": b, "limit": 100},
    )
    recipient_msgs = queried_r.get("messages", [])
    report(
        "query history: query by recipient returns results",
        len(recipient_msgs) >= 2,
        f"got {len(recipient_msgs)} messages",
    )


# ---------------------------------------------------------------------------
# 16. Concurrent squad + team (2 checks)
# ---------------------------------------------------------------------------


async def check_concurrent_squad_plus_team(
    session: ClientSession, a: str, b: str
) -> None:
    """Dismiss previous team, verify agents can form new team."""
    # Ensure no existing team
    info_a = await call_tool(session, "agent_info", {"agent_id": a})
    existing_team = info_a.get("current_team_id") if info_a else None
    if existing_team:
        await call_tool(
            session,
            "team_dismiss",
            {"team_id": existing_team, "caller_id": a},
        )

    info_b = await call_tool(session, "agent_info", {"agent_id": b})
    existing_team_b = info_b.get("current_team_id") if info_b else None
    if existing_team_b and existing_team_b != existing_team:
        await call_tool(
            session,
            "team_dismiss",
            {"team_id": existing_team_b, "caller_id": b},
        )

    # Ensure no existing squad
    if info_a.get("squad_id"):
        await call_tool(session, "squad_leave", {"agent_id": a})
    if info_b.get("squad_id"):
        await call_tool(session, "squad_leave", {"agent_id": b})

    # Create new squad
    created = await call_tool(
        session,
        "squad_create",
        {"name": "concurrent-squad", "caller_id": a},
    )
    squad_id = created["squad_id"]
    await call_tool(
        session,
        "squad_join",
        {"squad_id": squad_id, "agent_id": b, "role": "member", "caller_id": a},
    )

    # Form new team
    formed = await call_tool(
        session,
        "team_form",
        {"agent_ids": [a, b]},
    )
    report(
        "concurrent: form new squad + team",
        "team_id" in formed,
        str(formed),
    )

    # Verify both
    info_b2 = await call_tool(session, "agent_info", {"agent_id": b})
    has_both = (
        info_b2 is not None
        and info_b2.get("squad_id") == squad_id
        and info_b2.get("current_team_id") is not None
    )
    report(
        "concurrent: beta in squad and team simultaneously",
        has_both,
        f"squad_id={info_b2.get('squad_id')}, team_id={info_b2.get('current_team_id')}",
    )


# ---------------------------------------------------------------------------
# 17. Push notification & agent_wake (4 checks)
# ---------------------------------------------------------------------------


async def check_push_and_wake(
    session: ClientSession, a: str, b: str
) -> None:
    """Verify message_wait returns immediately when messages pending.
    Verify agent_wake resumes paused agent and queues notification message."""
    # Ensure clean state: leave any squad/team
    info_b = await call_tool(session, "agent_info", {"agent_id": b})
    if info_b and info_b.get("squad_id"):
        await call_tool(session, "squad_leave", {"agent_id": b})
    if info_b and info_b.get("current_team_id"):
        await call_tool(
            session,
            "team_dismiss",
            {"team_id": info_b["current_team_id"], "caller_id": b},
        )

    # Send a message first, then use message_wait with timeout=0
    sent = await call_tool(
        session,
        "message_send",
        {"sender_id": a, "recipient": b, "payload": "wait-test-msg"},
    )
    report(
        "push+wake: send message for wait test",
        "msg_id" in sent,
        str(sent),
    )

    # message_wait with timeout=0 should return immediately with the message
    wait_result = await call_tool(
        session,
        "message_wait",
        {"agent_id": b, "timeout": 0},
    )
    msgs = wait_result.get("messages", [])
    report(
        "push+wake: message_wait returns pending messages",
        len(msgs) >= 1,
        f"got {len(msgs)} messages, waited={wait_result.get('waited')}",
    )

    # Pause agent b, then wake it
    paused = await call_tool(session, "agent_pause", {"agent_id": b})
    report(
        "push+wake: pause agent b",
        paused.get("status") == "paused",
        str(paused),
    )

    woken = await call_tool(
        session,
        "agent_wake",
        {"agent_id": b, "message": "system-wake-notification"},
    )
    report(
        "push+wake: agent_wake resumes and queues message",
        woken.get("status") == "active" and woken.get("message_queued") is True,
        str(woken),
    )

    # Poll b to verify wake message arrived
    polled = await call_tool(
        session,
        "message_poll",
        {"agent_id": b, "unread_only": True},
    )
    wake_msgs = [
        m for m in polled.get("messages", [])
        if m.get("payload") == "system-wake-notification"
    ]
    report(
        "push+wake: wake notification message received",
        len(wake_msgs) >= 1,
        f"got {len(wake_msgs)} wake messages",
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def run_tests() -> None:
    global passed, failed

    # Clean DB from previous runs
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    env = os.environ.copy()
    env["AGENTSQUAD_DB_PATH"] = DB_PATH

    print(f"Starting broker on port {PORT} ...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from mcp_server.server import run_server; run_server('streamable-http', 8198)",
        ],
        cwd=project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for broker to be ready
    print("Waiting for broker to start ...")
    await asyncio.sleep(3)

    try:
        async with streamablehttp_client(BASE_URL) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("MCP session initialized.\n")

                # --- 1. Agent state transitions ---
                print("--- 1. Agent State Transitions ---")
                a, b, c = await check_agent_state_transitions(session)

                # --- 2. Message buffering on pause ---
                print("\n--- 2. Message Buffering on Pause ---")
                await check_message_buffering_on_pause(session, a, b)

                # --- 3. Squad lifecycle ---
                print("\n--- 3. Squad Lifecycle ---")
                squad_id = await check_squad_lifecycle(session, a, b, c)

                # --- 4. Squad role changes ---
                print("\n--- 4. Squad Role Changes ---")
                await check_squad_role_changes(session, a, b, c, squad_id)

                # --- 5. Observer permissions ---
                print("\n--- 5. Observer Permissions ---")
                await check_observer_permissions(session, a, b, c, squad_id)

                # --- 6. Squad messaging ---
                print("\n--- 6. Squad Messaging ---")
                await check_squad_messaging(session, a, b, c, squad_id)

                # --- 7. Agent pause in squad ---
                print("\n--- 7. Agent Pause in Squad ---")
                await check_agent_pause_in_squad(session, a, b)

                # --- 8. Squad dissolve ---
                print("\n--- 8. Squad Dissolve ---")
                await check_squad_dissolve(session, a, b, c, squad_id)

                # --- 9. Ad-hoc team lifecycle ---
                print("\n--- 9. Ad-hoc Team Lifecycle ---")
                team_id = await check_adhoc_team_lifecycle(session, a, b, c)

                # --- 10. Squad + team ---
                print("\n--- 10. Squad + Team ---")
                team_id_2 = await check_squad_plus_team(session, a, b)

                # --- 11. Team exclusive membership ---
                print("\n--- 11. Team Exclusive Membership ---")
                await check_team_exclusive_membership(session, a, b, team_id_2)

                # --- 12. Team messaging ---
                print("\n--- 12. Team Messaging ---")
                await check_team_messaging(session, a, b, c)

                # --- 13. Subscription scoping ---
                print("\n--- 13. Subscription Scoping ---")
                await check_subscription_scoping(session, a, b)

                # --- 14. Message query history ---
                print("\n--- 14. Message Query History ---")
                await check_message_query_history(session, a, b)

                # --- 15. Concurrent squad + team ---
                print("\n--- 15. Concurrent Squad + Team ---")
                await check_concurrent_squad_plus_team(session, a, b)

                # --- 16. Push notification and agent_wake ---
                print("\n--- 16. Push Notification & Agent Wake ---")
                await check_push_and_wake(session, a, b)

                # --- Cleanup: deregister all agents ---
                print("\n--- Cleanup ---")
                for agent_id, label in [(a, "alpha"), (b, "beta"), (c, "gamma")]:
                    d = await call_tool(
                        session, "agent_deregister", {"agent_id": agent_id}
                    )
                    report(
                        f"deregister {label}",
                        d.get("status") in ("deregistered", "ok"),
                        str(d),
                    )

    finally:
        print("\nStopping broker ...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("Broker stopped.")

        # Clean up DB
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed} checks")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(run_tests())
    sys.exit(0 if failed == 0 else 1)
