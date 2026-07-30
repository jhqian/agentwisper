# Copyright 2026 agentwisper contributors
# Licensed under the Apache License, Version 2.0

"""Signal file writer for lightweight agent notification flags."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio


class SignalWriter:
    """Writes atomic JSON signal files as 'has mail' flags for agents.

    Signal files are co-located with the database in a .signals/ directory.
    Each file is a minimal JSON flag: {"pending": true, "last_arrival": "..."}
    Atomic write uses tmp + rename to prevent partial reads.
    """

    def __init__(self, signal_dir: Path) -> None:
        self._dir = anyio.Path(signal_dir)
        self._sync_dir = signal_dir
        self._sync_dir.mkdir(parents=True, exist_ok=True)

    async def write(self, agent_id: str) -> None:
        """Atomic write: tmp file + rename."""
        signal = {"pending": True, "last_arrival": _now()}
        target = self._dir / f"{agent_id}.json"
        tmp = self._dir / f"{agent_id}.json.tmp"
        await tmp.write_text(json.dumps(signal))
        await tmp.rename(target)

    async def clear(self, agent_id: str) -> None:
        """Remove signal file (called after message_poll returns messages)."""
        target = self._dir / f"{agent_id}.json"
        try:
            await target.unlink()
        except FileNotFoundError:
            pass

    async def check(self, agent_id: str) -> dict[str, Any] | None:
        """Read signal file. Returns None if no signal exists."""
        target = self._dir / f"{agent_id}.json"
        try:
            content = await target.read_text()
            return json.loads(content)
        except FileNotFoundError:
            return None

    async def cleanup_agent(self, agent_id: str) -> None:
        """Remove signal file on agent deregister."""
        await self.clear(agent_id)

    async def cleanup_all(self) -> None:
        """Remove all signal files (called on broker start for stale cleanup)."""
        async for f in self._dir.glob("*.json"):
            await f.unlink()

    def pending_count(self) -> int:
        """Return count of pending signal files (for broker_status)."""
        return sum(1 for _ in self._sync_dir.glob("*.json"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
