# Background loop (every 2 s real): move vehicles along their route on the sim clock, emit simulated contactless
# vitals when no Presage bridge is connected, auto-arrive at ETA. State lives on the transfer, so restarts are safe.
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("atollcare.sim")


class SimLoop:
    def __init__(self, transfers, tick_s: float = 2.0) -> None:
        self.transfers = transfers
        self.tick_s = tick_s
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.transfers.tick()
            except Exception:
                log.exception("sim tick failed")
            await asyncio.sleep(self.tick_s)
