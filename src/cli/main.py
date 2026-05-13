# Copyright 2026 agentsquad contributors
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
    "--port",
    default=8000,
    type=int,
    help="HTTP port for the broker server",
)
def start(port: int) -> None:
    """Start the broker MCP server."""
    import os

    from mcp_server.server import run_server

    os.environ.setdefault("AGENTSQUAD_HTTP_PORT", str(port))
    run_server(port=port)


@cli.command()
def status() -> None:
    """Show broker status (requires running broker)."""
    click.echo("Broker status: not yet implemented (requires client connection)")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
