from __future__ import annotations

from recall.scheduler.config import ScheduleEntry
from recall.commands.ingest_confluence import _run_confluence_ingest
from recall.commands.ingest import _run_local_ingest


def dispatch(entry: ScheduleEntry) -> str:
    prefix, _, mode = entry.job.partition(":")

    if prefix == "confluence" and mode in {"page", "folder", "space", "label"}:
        return _run_confluence_ingest(mode=mode, params=entry.params)

    if prefix == "local" and mode in {"all", "project", "source"}:
        return _run_local_ingest(mode=mode, params=entry.params)

    raise ValueError(f"unknown job type '{entry.job}'")
