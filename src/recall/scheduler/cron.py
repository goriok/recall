from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter


class CronError(Exception):
    pass


def validate_cron(expr: str) -> None:
    parts = expr.strip().split()
    if len(parts) != 5:
        raise CronError(f"cron expression must have exactly 5 fields, got {len(parts)}: '{expr}'")
    if not croniter.is_valid(expr):
        raise CronError(f"invalid cron expression: '{expr}'")


def next_fire(expr: str, from_dt: datetime) -> datetime:
    validate_cron(expr)
    base = from_dt.timestamp()
    itr = croniter(expr, base)
    ts: float = itr.get_next(float)
    return datetime.fromtimestamp(ts, tz=timezone.utc)
