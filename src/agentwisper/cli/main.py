# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""CLI entry point for Vibe AgentWhisper broker."""

from __future__ import annotations

import click


def _get_version() -> str:
    from agentwisper.common.version import get_version
    return get_version()


@click.group()
@click.version_option(version=_get_version(), prog_name="agentwisper")
def cli() -> None:
    """Vibe AgentWhisper - Multi-agent communication platform."""
    pass


@cli.command()
@click.option(
    "--port",
    default=8000,
    type=int,
    help="HTTP port for the broker server",
)
@click.option(
    "--host",
    default="127.0.0.1",
    type=str,
    help="Host address to bind (use 0.0.0.0 for remote access)",
)
def start(port: int, host: str) -> None:
    """Start the broker MCP server."""
    import os

    from agentwisper.mcp_server.server import run_server

    os.environ.setdefault("AGENTWHISPER_HTTP_PORT", str(port))
    os.environ.setdefault("AGENTWHISPER_HTTP_HOST", host)
    run_server(port=port, host=host)


@cli.command()
def status() -> None:
    """Show broker status (requires running broker)."""
    click.echo("Broker status: not yet implemented (requires client connection)")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
