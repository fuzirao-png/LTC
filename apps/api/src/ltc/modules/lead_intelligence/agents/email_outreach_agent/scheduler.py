from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from ltc.modules.lead_intelligence.agents.email_outreach_agent.agent import AutoTouchConfig


LOGGER = logging.getLogger(__name__)


class EmailAutomationScheduler:
    def __init__(
        self,
        *,
        load_config: Callable[[], AutoTouchConfig],
        run_once: Callable[[AutoTouchConfig], Awaitable[dict]],
        poll_seconds: int = 30,
    ) -> None:
        self._load_config = load_config
        self._run_once = run_once
        self._poll_seconds = max(5, poll_seconds)
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._last_run_at: datetime | None = None

    async def start(self) -> None:
        if self._task is None:
            self._stopped.clear()
            self._task = asyncio.create_task(self._loop(), name="email-automation-agent")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        try:
            while not self._stopped.is_set():
                await asyncio.sleep(self._poll_seconds)
                config = self._load_config()
                if not config.enabled:
                    continue
                now = datetime.now(timezone.utc)
                interval_minutes = max(1, int(getattr(config, "interval_minutes", 60)))
                if self._last_run_at is not None and now < self._last_run_at + timedelta(minutes=interval_minutes):
                    continue
                try:
                    await self._run_once(config)
                    self._last_run_at = now
                except Exception:
                    LOGGER.exception("email automation agent run failed")
        except asyncio.CancelledError:
            raise
