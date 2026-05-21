from __future__ import annotations

from recall.scheduler.config import ScheduleEntry
from recall.commands.ingest_confluence import _run_confluence_ingest


def dispatch(entry: ScheduleEntry) -> str:
    prefix, _, mode = entry.job.partition(":")
    if prefix != "confluence" or mode not in ("page", "folder", "space", "label"):
        raise ValueError(f"unknown job type '{entry.job}'")

    return _run_confluence_ingest(mode=mode, params=entry.params)
