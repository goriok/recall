from __future__ import annotations

import pytest
from datetime import datetime, timezone
from recall.scheduler.cron import next_fire, validate_cron, CronError


def test_next_fire_on_the_hour():
    # cron "0 */3 * * *" — fires at 00:00, 03:00, 06:00 ...
    # from 2026-01-01 00:00:00 UTC, next fire is 2026-01-01 03:00:00 UTC
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire("0 */3 * * *", now)
    assert nxt == datetime(2026, 1, 1, 3, 0, 0, tzinfo=timezone.utc)


def test_next_fire_with_minute_offset():
    # "15 */3 * * *" — fires at 00:15, 03:15, 06:15 ...
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire("15 */3 * * *", now)
    assert nxt == datetime(2026, 1, 1, 0, 15, 0, tzinfo=timezone.utc)


def test_next_fire_crosses_day_boundary():
    now = datetime(2026, 1, 1, 23, 30, 0, tzinfo=timezone.utc)
    nxt = next_fire("0 */3 * * *", now)
    assert nxt == datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)


def test_next_fire_daily():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire("0 6 * * *", now)
    assert nxt == datetime(2026, 1, 2, 6, 0, 0, tzinfo=timezone.utc)


def test_next_fire_returns_utc_aware():
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire("0 * * * *", now)
    assert nxt.tzinfo is not None


def test_validate_cron_accepts_valid_expression():
    validate_cron("0 */3 * * *")  # no exception


def test_validate_cron_accepts_daily():
    validate_cron("0 6 * * *")


def test_validate_cron_rejects_six_field():
    with pytest.raises(CronError):
        validate_cron("0 0 * * * *")


def test_validate_cron_rejects_four_field():
    with pytest.raises(CronError):
        validate_cron("0 * * *")


def test_validate_cron_rejects_garbage():
    with pytest.raises(CronError):
        validate_cron("not-a-cron")
