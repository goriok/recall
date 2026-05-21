from __future__ import annotations

import pytest
from pathlib import Path
from recall.scheduler.config import ScheduleEntry, parse_schedules, ScheduleConfigError


# --- parse_schedules ---

def test_parse_valid_page_schedule():
    data = {
        "schedules": [
            {
                "name": "anchor-rfcs",
                "cron": "0 */3 * * *",
                "job": "confluence:page",
                "page_id": "5668602002",
            }
        ]
    }
    entries = parse_schedules(data)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "anchor-rfcs"
    assert entry.cron == "0 */3 * * *"
    assert entry.job == "confluence:page"
    assert entry.params["page_id"] == "5668602002"


def test_parse_valid_folder_schedule():
    data = {
        "schedules": [
            {
                "name": "mimeh-folder",
                "cron": "15 */3 * * *",
                "job": "confluence:folder",
                "folder_id": "5835685962",
                "recreate": False,
            }
        ]
    }
    entries = parse_schedules(data)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.params["folder_id"] == "5835685962"
    assert entry.params.get("recreate") is False


def test_parse_valid_space_schedule():
    data = {
        "schedules": [
            {
                "name": "eng-space",
                "cron": "0 6 * * *",
                "job": "confluence:space",
                "space": "ENG",
            }
        ]
    }
    entries = parse_schedules(data)
    assert entries[0].params["space"] == "ENG"


def test_parse_empty_schedules_list():
    entries = parse_schedules({"schedules": []})
    assert entries == []


def test_parse_missing_schedules_key():
    entries = parse_schedules({})
    assert entries == []


def test_parse_raises_for_missing_name():
    with pytest.raises(ScheduleConfigError, match="name"):
        parse_schedules({"schedules": [{"cron": "0 * * * *", "job": "confluence:page", "page_id": "1"}]})


def test_parse_raises_for_missing_cron():
    with pytest.raises(ScheduleConfigError, match="cron"):
        parse_schedules({"schedules": [{"name": "x", "job": "confluence:page", "page_id": "1"}]})


def test_parse_raises_for_missing_job():
    with pytest.raises(ScheduleConfigError, match="job"):
        parse_schedules({"schedules": [{"name": "x", "cron": "0 * * * *"}]})


def test_parse_raises_for_unknown_job_type():
    with pytest.raises(ScheduleConfigError, match="unknown job"):
        parse_schedules({"schedules": [{"name": "x", "cron": "0 * * * *", "job": "jira:bogus"}]})


def test_parse_raises_for_page_job_without_page_id():
    with pytest.raises(ScheduleConfigError, match="page_id"):
        parse_schedules({"schedules": [{"name": "x", "cron": "0 * * * *", "job": "confluence:page"}]})


def test_parse_raises_for_folder_job_without_folder_id():
    with pytest.raises(ScheduleConfigError, match="folder_id"):
        parse_schedules({"schedules": [{"name": "x", "cron": "0 * * * *", "job": "confluence:folder"}]})


def test_parse_raises_for_space_job_without_space():
    with pytest.raises(ScheduleConfigError, match="space"):
        parse_schedules({"schedules": [{"name": "x", "cron": "0 * * * *", "job": "confluence:space"}]})


def test_parse_multiple_schedules():
    data = {
        "schedules": [
            {"name": "a", "cron": "0 * * * *", "job": "confluence:page", "page_id": "111"},
            {"name": "b", "cron": "30 * * * *", "job": "confluence:folder", "folder_id": "222"},
        ]
    }
    entries = parse_schedules(data)
    assert len(entries) == 2
    assert entries[0].name == "a"
    assert entries[1].name == "b"


def test_optional_collection_param():
    data = {
        "schedules": [
            {
                "name": "x",
                "cron": "0 * * * *",
                "job": "confluence:page",
                "page_id": "111",
                "collection": "my-col",
            }
        ]
    }
    entries = parse_schedules(data)
    assert entries[0].params["collection"] == "my-col"
