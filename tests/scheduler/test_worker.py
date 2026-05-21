from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from recall.scheduler.config import ScheduleEntry
from recall.scheduler.worker import run_schedule_loop


# --- helpers ---

def make_entry(name="test-job", cron="0 * * * *", job="confluence:page", **params):
    return ScheduleEntry(name=name, cron=cron, job=job, params={"page_id": "111", **params})


# --- run_schedule_loop fires job and notifies ---

async def test_loop_fires_job_and_calls_callbacks():
    fired: list[str] = []
    started: list[str] = []
    results: list[str] = []

    entry = make_entry()

    def fake_dispatch(e):
        fired.append(e.name)
        return "42 chunks indexed"

    callbacks = {
        "on_start": AsyncMock(side_effect=lambda name: started.append(name)),
        "on_result": AsyncMock(side_effect=lambda name, **kw: results.append(name)),
        "on_error": AsyncMock(),
    }

    # patch next_fire to return "now" so the loop fires immediately
    stop_event = asyncio.Event()
    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            stop_event.set()

    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    with (
        patch("recall.scheduler.worker.next_fire", return_value=now),
        patch("recall.scheduler.worker.asyncio.sleep", side_effect=fake_sleep),
        patch("recall.scheduler.worker.dispatch", side_effect=fake_dispatch),
    ):
        task = asyncio.create_task(
            run_schedule_loop(entry, callbacks=callbacks, stop_event=stop_event)
        )
        await asyncio.wait_for(stop_event.wait(), timeout=2.0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert entry.name in started
    assert entry.name in results
    callbacks["on_error"].assert_not_called()


async def test_loop_calls_on_error_when_dispatch_raises():
    entry = make_entry()
    errors: list[str] = []

    def bad_dispatch(e):
        raise RuntimeError("boom")

    callbacks = {
        "on_start": AsyncMock(),
        "on_result": AsyncMock(),
        "on_error": AsyncMock(side_effect=lambda name, **kw: errors.append(name)),
    }

    stop_event = asyncio.Event()
    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            stop_event.set()

    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    with (
        patch("recall.scheduler.worker.next_fire", return_value=now),
        patch("recall.scheduler.worker.asyncio.sleep", side_effect=fake_sleep),
        patch("recall.scheduler.worker.dispatch", side_effect=bad_dispatch),
    ):
        task = asyncio.create_task(
            run_schedule_loop(entry, callbacks=callbacks, stop_event=stop_event)
        )
        await asyncio.wait_for(stop_event.wait(), timeout=2.0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert entry.name in errors
    callbacks["on_result"].assert_not_called()
