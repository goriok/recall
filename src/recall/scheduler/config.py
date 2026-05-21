from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_KNOWN_JOBS = {
    "confluence:page",
    "confluence:folder",
    "confluence:space",
    "confluence:label",
}

_REQUIRED_PARAMS: dict[str, str] = {
    "confluence:page": "page_id",
    "confluence:folder": "folder_id",
    "confluence:space": "space",
    "confluence:label": "label",
}

_PARAM_KEYS = {"page_id", "folder_id", "space", "label", "collection", "recreate"}


class ScheduleConfigError(Exception):
    pass


@dataclass
class ScheduleEntry:
    name: str
    cron: str
    job: str
    params: dict[str, Any] = field(default_factory=dict)


def parse_schedules(data: dict) -> list[ScheduleEntry]:
    raw = data.get("schedules", [])
    entries: list[ScheduleEntry] = []

    for i, item in enumerate(raw):
        if "name" not in item:
            raise ScheduleConfigError(f"schedule[{i}]: missing required field 'name'")
        if "cron" not in item:
            raise ScheduleConfigError(f"schedule '{item.get('name', i)}': missing required field 'cron'")
        if "job" not in item:
            raise ScheduleConfigError(f"schedule '{item['name']}': missing required field 'job'")

        job = item["job"]
        if job not in _KNOWN_JOBS:
            raise ScheduleConfigError(
                f"schedule '{item['name']}': unknown job type '{job}'. "
                f"Valid values: {sorted(_KNOWN_JOBS)}"
            )

        required_param = _REQUIRED_PARAMS[job]
        if required_param not in item:
            raise ScheduleConfigError(
                f"schedule '{item['name']}' (job={job}): missing required param '{required_param}'"
            )

        params = {k: item[k] for k in _PARAM_KEYS if k in item}

        entries.append(ScheduleEntry(name=item["name"], cron=item["cron"], job=job, params=params))

    return entries
