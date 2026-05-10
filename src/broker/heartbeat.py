# Licensed under the Apache License, Version 2.0

"""Heartbeat monitor for detecting stale agents."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from common.types import AgentStatus
from persistence.database import AsyncDatabase


class HeartbeatMonitor:
    """Background task that detects agents with stale heartbeats
    and marks them disconnected."""

    def __init__(
        self,
        db: AsyncDatabase,
        interval: int = 30,
        timeout: int = 90,
    ) -> None:
        self._db = db
        self._interval = interval
        self._timeout = timeout
        self._running = False
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background monitoring loop."""
        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        """Internal loop: scan agents at each interval, mark stale ones."""
        while not self._stop_event.is_set():
            try:
                await self.check_agents()
            except Exception:
                pass
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._interval
                )
            except asyncio.TimeoutError:
                pass

    async def check_agents(self) -> int:
        """One scan cycle. Returns count of newly disconnected agents."""
        threshold = (
            datetime.now(timezone.utc) - timedelta(seconds=self._timeout)
        ).isoformat()
        rows = await self._db.execute_fetchall(
            "SELECT agent_id FROM agents WHERE status = ? AND last_heartbeat < ?",
            (AgentStatus.ACTIVE, threshold),
        )
        for row in rows:
            await self._db.execute(
                "UPDATE agents SET status = ? WHERE agent_id = ?",
                (AgentStatus.DISCONNECTED, row["agent_id"]),
            )
        return len(rows)
