# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Client test for MCP log notification delivery over streamable-http.

Tests whether notifications sent by the server via send_log_message()
are actually received by the client via the SSE stream.

Usage:
    1. Start server: uv run python tests/push_test_server.py (port 8002)
    2. Run client:  uv run python tests/test_push_notification.py
"""

from __future__ import annotations

import asyncio
import sys


async def main():
    try:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp import ClientSession
        from mcp.types import LoggingMessageNotificationParams
    except ImportError:
        print("ERROR: mcp package not installed. Run: uv sync")
        sys.exit(1)

    url = "http://localhost:8002/mcp"

    log_messages: list[str] = []
    raw_notifications: list[str] = []

    async def on_log(params: LoggingMessageNotificationParams) -> None:
        """Called when server sends a log message notification."""
        log_messages.append(f"level={params.level} data={params.data}")
        print(f"  >>> LOG NOTIFICATION: level={params.level} data={params.data}")

    async def on_message(notification) -> None:
        """Called for any server notification."""
        raw_notifications.append(str(notification))
        print(f"  >>> RAW NOTIFICATION: {type(notification).__name__}")

    print(f"Connecting to {url}...")
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(
            read_stream,
            write_stream,
            logging_callback=on_log,
            message_handler=on_message,
        ) as session:
            await session.initialize()
            print("Connected and initialized.\n")

            tools_result = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools_result.tools]}\n")

            # Test 1: Log notification linked to request
            print("Test 1: trigger_notification (linked to request)")
            result = await session.call_tool(
                "trigger_notification",
                arguments={"message": "Test log from client", "level": "info"},
            )
            print(f"  Tool result: {[c.text for c in result.content if hasattr(c, 'text')]}")
            await asyncio.sleep(1)

            # Test 2: Unsolicited log notification
            print("\nTest 2: trigger_unsolicited_notification")
            result = await session.call_tool(
                "trigger_unsolicited_notification",
                arguments={"message": "Unsolicited test", "level": "warning"},
            )
            print(f"  Tool result: {[c.text for c in result.content if hasattr(c, 'text')]}")
            await asyncio.sleep(1)

            # Test 3: Resource updated notification
            print("\nTest 3: trigger_resource_notification")
            result = await session.call_tool(
                "trigger_resource_notification",
                arguments={"uri": "test://push-verify"},
            )
            print(f"  Tool result: {[c.text for c in result.content if hasattr(c, 'text')]}")
            await asyncio.sleep(1)

    print(f"\n=== Results ===")
    print(f"Log notifications received: {len(log_messages)}")
    for m in log_messages:
        print(f"  {m}")
    print(f"Raw notifications received: {len(raw_notifications)}")
    for n in raw_notifications:
        print(f"  {n}")

    if log_messages:
        print("\nPASS: Server log notifications delivered via MCP SSE stream.")
    else:
        print("\nFAIL: No log notifications received.")
    if raw_notifications:
        print(f"PASS: {len(raw_notifications)} raw notifications received.")
    else:
        print("FAIL: No raw notifications received.")


if __name__ == "__main__":
    asyncio.run(main())
