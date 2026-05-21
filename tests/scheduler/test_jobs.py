from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from recall.scheduler.config import ScheduleEntry
from recall.scheduler.jobs import dispatch


def make_entry(job, **params):
    return ScheduleEntry(name="test", cron="0 * * * *", job=job, params=params)


def test_dispatch_confluence_page_calls_core(tmp_path):
    entry = make_entry("confluence:page", page_id="5668602002")

    with patch("recall.scheduler.jobs._run_confluence_ingest") as mock_run:
        mock_run.return_value = "10 chunks indexed"
        result = dispatch(entry)

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["mode"] == "page"
    assert call_kwargs["params"]["page_id"] == "5668602002"
    assert "10 chunks" in result


def test_dispatch_confluence_folder_calls_core():
    entry = make_entry("confluence:folder", folder_id="5835685962")

    with patch("recall.scheduler.jobs._run_confluence_ingest") as mock_run:
        mock_run.return_value = "5 chunks indexed"
        dispatch(entry)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["mode"] == "folder"
    assert call_kwargs["params"]["folder_id"] == "5835685962"


def test_dispatch_confluence_space_calls_core():
    entry = make_entry("confluence:space", space="MIMEH")

    with patch("recall.scheduler.jobs._run_confluence_ingest") as mock_run:
        mock_run.return_value = "20 chunks indexed"
        dispatch(entry)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["mode"] == "space"
    assert call_kwargs["params"]["space"] == "MIMEH"


def test_dispatch_confluence_label_calls_core():
    entry = make_entry("confluence:label", label="architecture")

    with patch("recall.scheduler.jobs._run_confluence_ingest") as mock_run:
        mock_run.return_value = "3 chunks indexed"
        dispatch(entry)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["mode"] == "label"
    assert call_kwargs["params"]["label"] == "architecture"


def test_dispatch_raises_for_unknown_job():
    entry = make_entry("confluence:unknown")

    with pytest.raises(ValueError, match="unknown job"):
        dispatch(entry)


# --- local:* dispatch ---

def test_dispatch_local_all_calls_core():
    entry = make_entry("local:all")

    with patch("recall.scheduler.jobs._run_local_ingest") as mock_run:
        mock_run.return_value = "3 project(s) indexed, 90 chunks total"
        result = dispatch(entry)

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["mode"] == "all"
    assert call_kwargs["params"] == {}
    assert "project(s) indexed" in result


def test_dispatch_local_project_calls_core():
    entry = make_entry("local:project", project="recall")

    with patch("recall.scheduler.jobs._run_local_ingest") as mock_run:
        mock_run.return_value = "1 project(s) indexed, 42 chunks total"
        dispatch(entry)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["mode"] == "project"
    assert call_kwargs["params"]["project"] == "recall"


def test_dispatch_local_source_calls_core():
    entry = make_entry("local:source", source="~/sources")

    with patch("recall.scheduler.jobs._run_local_ingest") as mock_run:
        mock_run.return_value = "5 project(s) indexed, 200 chunks total"
        dispatch(entry)

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["mode"] == "source"
    assert call_kwargs["params"]["source"] == "~/sources"


def test_dispatch_local_does_not_call_confluence_core():
    entry = make_entry("local:all")

    with (
        patch("recall.scheduler.jobs._run_local_ingest", return_value="ok"),
        patch("recall.scheduler.jobs._run_confluence_ingest") as mock_cf,
    ):
        dispatch(entry)

    mock_cf.assert_not_called()
