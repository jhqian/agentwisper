# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Minimal MCP server to test if Claude Code consumes server-sent log
notifications over streamable-http transport.

Usage:
    uv run python tests/push_test_server.py

Then connect Claude Code to http://localhost:8001/mcp and call the
trigger_notification tool. Observe whether the log message appears
in Claude Code's output.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP, Context


@asynccontextmanager
async def app_lifespan(app: FastMCP):
    yield {"notification_count": 0}


mcp = FastMCP(
    name="push-test",
    lifespan=app_lifespan,
)


@mcp.tool()
async def trigger_notification(
    message: str = "Hello from push test!",
    level: str = "info",
    ctx: Context | None = None,
) -> str:
    """Trigger a server-sent log notification.

    Call this tool and observe whether the log notification appears
    in the client's output.
    """
    if ctx is None:
        return "Error: no context"

    await ctx.session.send_log_message(
        level=level,
        data=message,
        logger="push-test",
        related_request_id=ctx.request_id,
    )
    return f"Sent log notification: level={level}, message={message}"


@mcp.tool()
async def trigger_unsolicited_notification(
    message: str = "Unsolicited notification!",
    level: str = "info",
    ctx: Context | None = None,
) -> str:
    """Trigger a log notification NOT linked to the current request.

    This tests whether unsolicited (no related_request_id) notifications
    are delivered to the client.
    """
    if ctx is None:
        return "Error: no context"

    await ctx.session.send_log_message(
        level=level,
        data=message,
        logger="push-test",
    )
    return f"Sent unsolicited log notification: level={level}, message={message}"


@mcp.tool()
async def trigger_resource_notification(
    uri: str = "test://resource",
    ctx: Context | None = None,
) -> str:
    """Trigger a resource-updated notification.

    Tests whether notifications/resources/updated is consumed.
    """
    if ctx is None:
        return "Error: no context"

    from mcp.types import AnyUrl
    await ctx.session.send_resource_updated(uri=AnyUrl(uri))
    return f"Sent resource updated notification for: {uri}"


if __name__ == "__main__":
    import sys

    print("Starting push-test MCP server on port 8002...")
    print("Connect Claude Code to: http://localhost:8002/mcp")
    print("")
    print("Test steps:")
    print("1. Create /tmp/push_test directory with .mcp.json:")
    print('   {"mcpServers":{"push-test":{"type":"http","url":"http://localhost:8001/mcp"}}}')
    print("2. cd /tmp/push_test && claude")
    print("3. Call trigger_notification tool")
    print("4. Check if log notification appears in Claude Code output")
    print("")

    mcp.settings.port = 8002
    mcp.run(transport="streamable-http")
