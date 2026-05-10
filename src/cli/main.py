# Copyright 2026 vibe-agentsquad contributors
# Licensed under the Apache License, Version 2.0

"""CLI entry point for Vibe AgentSquad broker."""

from __future__ import annotations

import click


@click.group()
def cli() -> None:
    """Vibe AgentSquad - Multi-agent communication platform."""
    pass


@cli.command()
@click.option(
    "--transport",
    default="stdio",
    type=click.Choice(["stdio", "sse", "streamable-http"]),
    help="Transport protocol",
)
@click.option(
    "--port",
    default=8000,
    type=int,
    help="HTTP port (for non-stdio transports)",
)
def start(transport: str, port: int) -> None:
    """Start the broker MCP server."""
    import os

    from mcp_server.server import run_server

    if transport != "stdio":
        os.environ["AGENTSQUAD_TRANSPORT"] = transport
        os.environ.setdefault("AGENTSQUAD_HTTP_PORT", str(port))

    run_server(transport=transport, port=port if transport != "stdio" else None)


@cli.command()
def status() -> None:
    """Show broker status (requires running broker)."""
    click.echo("Broker status: not yet implemented (requires client connection)")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
