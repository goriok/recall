from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from typing import Any

from recall.scheduler.config import ScheduleEntry
from recall.scheduler.cron import next_fire
from recall.scheduler.jobs import dispatch


async def run_schedule_loop(
    entry: ScheduleEntry,
    *,
    callbacks: dict[str, Any],
    stop_event: asyncio.Event,
) -> None:
    on_start = callbacks.get("on_start")
    on_result = callbacks.get("on_result")
    on_error = callbacks.get("on_error")

    while not stop_event.is_set():
        now = datetime.now(tz=timezone.utc)
        nxt = next_fire(entry.cron, now)
        delta = (nxt - now).total_seconds()

        try:
            await asyncio.sleep(max(0.0, delta))
        except asyncio.CancelledError:
            return

        if stop_event.is_set():
            return

        if on_start:
            await on_start(entry.name)

        t0 = time.monotonic()
        try:
            output = await asyncio.to_thread(dispatch, entry)
            duration_ms = int((time.monotonic() - t0) * 1000)
            if on_result:
                await on_result(entry.name, duration_ms=duration_ms, output=output or "")
        except Exception as exc:
            if on_error:
                await on_error(entry.name, error=exc)
            else:
                sys.stderr.write(f"[recall-scheduler] {entry.name} failed: {exc}\n")
