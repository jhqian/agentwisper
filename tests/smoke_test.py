# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""Smoke test: start a real broker subprocess and validate MCP tools.

Usage:
    cd /path/to/agentsquad && uv run python tests/smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = 8199
DB_PATH = "/tmp/vibe_smoke_test.db"
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
    return json.loads(text)


async def check_register_agents(session: ClientSession) -> tuple[str, str]:
    a = await call_tool(
        session,
        "agent_register",
        {"name": "claude-code-alpha", "capabilities": ["code", "review"]},
    )
    report("register alpha", "agent_id" in a, str(a))

    b = await call_tool(
        session,
        "agent_register",
        {"name": "claude-code-beta", "capabilities": ["test", "deploy"]},
    )
    report("register beta", "agent_id" in b, str(b))

    return a["agent_id"], b["agent_id"]


async def check_p2p(session: ClientSession, a: str, b: str) -> None:
    sent = await call_tool(
        session,
        "message_send",
        {"sender_id": a, "recipient": b, "payload": "hello-b"},
    )
    report("p2p send", "msg_id" in sent, str(sent))

    polled = await call_tool(
        session,
        "message_poll",
        {"agent_id": b, "unread_only": True},
    )
    msgs = polled.get("messages", [])
    report("p2p poll", len(msgs) >= 1, f"got {len(msgs)} messages")

    msg_id = msgs[0]["msg_id"]
    ack = await call_tool(session, "message_ack", {"msg_id": msg_id})
    report("p2p ack", ack.get("status") in ("acknowledged", "ok"), str(ack))


async def check_rpc(session: ClientSession, a: str, b: str) -> None:
    req = await call_tool(
        session,
        "message_send",
        {
            "sender_id": a,
            "recipient": b,
            "payload": "rpc-call",
            "msg_type": "rpc_request",
        },
    )
    report("rpc request", "msg_id" in req, str(req))

    polled = await call_tool(
        session,
        "message_poll",
        {"agent_id": b, "unread_only": True},
    )
    rpc_msgs = [
        m for m in polled.get("messages", []) if m.get("msg_type") == "rpc_request"
    ]
    report("rpc poll", len(rpc_msgs) >= 1, f"got {len(rpc_msgs)} rpc messages")

    parent_id = rpc_msgs[0]["msg_id"]
    reply = await call_tool(
        session,
        "message_reply",
        {"parent_msg_id": parent_id, "sender_id": b, "payload": "rpc-response"},
    )
    report("rpc reply", "msg_id" in reply, str(reply))

    resp_polled = await call_tool(
        session,
        "message_poll",
        {"agent_id": a, "unread_only": True},
    )
    rpc_resps = [
        m
        for m in resp_polled.get("messages", [])
        if m.get("msg_type") == "rpc_response"
    ]
    report(
        "rpc response poll",
        len(rpc_resps) >= 1,
        f"got {len(rpc_resps)} rpc responses",
    )


async def check_squad(session: ClientSession, a: str, b: str) -> None:
    created = await call_tool(
        session,
        "squad_create",
        {"name": "smoke-squad", "caller_id": a},
    )
    report("squad create", "squad_id" in created, str(created))
    squad_id = created["squad_id"]

    joined = await call_tool(
        session,
        "squad_join",
        {"squad_id": squad_id, "agent_id": b, "caller_id": a},
    )
    report("squad join", joined.get("status") in ("joined", "ok"), str(joined))

    # list agents in squad via agent_list
    listed = await call_tool(
        session,
        "agent_list",
        {"squad_id": squad_id},
    )
    agents = listed.get("agents", [])
    report(
        "squad info (agent_list)",
        len(agents) >= 2,
        f"squad has {len(agents)} agents",
    )

    left = await call_tool(session, "squad_leave", {"agent_id": b})
    report("squad leave", left.get("status") in ("left", "ok"), str(left))


async def check_pubsub(session: ClientSession, a: str, b: str) -> None:
    sub = await call_tool(
        session,
        "topic_subscribe",
        {"agent_id": b, "topic": "smoke-topic"},
    )
    report("pubsub subscribe", "sub_id" in sub, str(sub))

    broadcast = await call_tool(
        session,
        "message_broadcast",
        {"sender_id": a, "topic": "smoke-topic", "payload": "pubsub-msg"},
    )
    report("pubsub broadcast", "delivered" in broadcast or "msg_id" in broadcast, str(broadcast))

    await asyncio.sleep(0.2)

    polled = await call_tool(
        session,
        "message_poll",
        {"agent_id": b, "unread_only": True},
    )
    pubsub_msgs = [
        m for m in polled.get("messages", []) if m.get("topic") == "smoke-topic"
    ]
    report("pubsub poll", len(pubsub_msgs) >= 1, f"got {len(pubsub_msgs)} pubsub messages")


async def check_heartbeat(session: ClientSession, a: str) -> None:
    hb = await call_tool(session, "heartbeat", {"agent_id": a})
    report("heartbeat", hb.get("status") == "ok" or "last_seen" in hb, str(hb))


async def check_status(session: ClientSession) -> None:
    st = await call_tool(session, "broker_status", {})
    report("broker status", st.get("status") == "healthy", str(st))


async def check_info_list(session: ClientSession, a: str) -> None:
    info = await call_tool(session, "agent_info", {"agent_id": a})
    report("agent info", info is not None and "name" in info, str(info))

    listed = await call_tool(session, "agent_list", {})
    report("agent list", "agents" in listed, f"total {listed.get('total', '?')} agents")


async def check_cleanup(session: ClientSession, a: str, b: str) -> None:
    d1 = await call_tool(session, "agent_deregister", {"agent_id": a})
    report("deregister alpha", d1.get("status") in ("deregistered", "ok"), str(d1))

    d2 = await call_tool(session, "agent_deregister", {"agent_id": b})
    report("deregister beta", d2.get("status") in ("deregistered", "ok"), str(d2))


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
            "from mcp_server.server import run_server; run_server('streamable-http', 8199)",
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

                print("--- Agent Registration ---")
                a, b = await check_register_agents(session)

                print("--- P2P Messaging ---")
                await check_p2p(session, a, b)

                print("--- RPC Messaging ---")
                await check_rpc(session, a, b)

                print("--- Squad Management ---")
                await check_squad(session, a, b)

                print("--- Pub/Sub ---")
                await check_pubsub(session, a, b)

                print("--- Heartbeat ---")
                await check_heartbeat(session, a)

                print("--- Status & Info ---")
                await check_status(session)
                await check_info_list(session, a)

                print("--- Cleanup ---")
                await check_cleanup(session, a, b)
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
