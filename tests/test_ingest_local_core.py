from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from recall.config import ConfigError
from recall.commands.ingest import _run_local_ingest


def _make_project(name: str, exists: bool = True):
    p = MagicMock()
    p.name = name
    p.resolved_path = MagicMock()
    p.resolved_path.exists.return_value = exists
    return p


def _make_config(projects=None, projects_from_source=None):
    cfg = MagicMock()
    cfg.qdrant.url = "http://localhost:6333"
    cfg.all_projects.return_value = projects or []
    if projects_from_source is not None:
        cfg.projects_from_source.return_value = projects_from_source
    return cfg


def test_local_all_sums_chunks_from_all_projects():
    p1 = _make_project("proj-a")
    p2 = _make_project("proj-b")
    cfg = _make_config(projects=[p1, p2])

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
        patch("recall.commands.ingest.index_project", side_effect=[10, 20]) as mock_idx,
    ):
        result = _run_local_ingest(mode="all", params={})

    assert mock_idx.call_count == 2
    assert "2 project(s) indexed" in result
    assert "30 chunks total" in result


def test_local_project_calls_single_project():
    proj = _make_project("recall")
    cfg = _make_config()
    cfg.project.return_value = proj

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
        patch("recall.commands.ingest.index_project", return_value=42),
    ):
        result = _run_local_ingest(mode="project", params={"project": "recall"})

    cfg.project.assert_called_once_with("recall")
    assert "1 project(s) indexed" in result
    assert "42 chunks total" in result


def test_local_source_filters_by_source_root():
    p1 = _make_project("src-a")
    p2 = _make_project("src-b")
    cfg = _make_config(projects_from_source=[p1, p2])

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
        patch("recall.commands.ingest.index_project", return_value=5),
    ):
        result = _run_local_ingest(mode="source", params={"source": "~/sources"})

    cfg.projects_from_source.assert_called_once_with("~/sources")
    assert "2 project(s) indexed" in result


def test_local_project_propagates_config_error():
    cfg = _make_config()
    cfg.project.side_effect = ConfigError("unknown project 'missing'")

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
    ):
        with pytest.raises(ConfigError, match="missing"):
            _run_local_ingest(mode="project", params={"project": "missing"})


def test_local_invalid_mode_raises_value_error():
    cfg = _make_config()

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
    ):
        with pytest.raises(ValueError, match="unknown local ingest mode"):
            _run_local_ingest(mode="bogus", params={})


def test_local_all_only_filter_restricts_projects():
    p1 = _make_project("hyle")
    p2 = _make_project("notes")
    p3 = _make_project("trivia")
    cfg = _make_config(projects=[p1, p2, p3])

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
        patch("recall.commands.ingest.index_project", return_value=10) as mock_idx,
    ):
        result = _run_local_ingest(mode="all", params={"only": ["hyle", "notes"]})

    assert mock_idx.call_count == 2
    called_names = {call[0][0].name for call in mock_idx.call_args_list}
    assert called_names == {"hyle", "notes"}
    assert "trivia" not in [call[0][0].name for call in mock_idx.call_args_list]
    assert "2 project(s) indexed" in result


def test_local_all_skip_filter_excludes_projects():
    p1 = _make_project("hyle")
    p2 = _make_project("notes")
    p3 = _make_project("trivia")
    cfg = _make_config(projects=[p1, p2, p3])

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
        patch("recall.commands.ingest.index_project", return_value=5) as mock_idx,
    ):
        result = _run_local_ingest(mode="all", params={"skip": ["trivia"]})

    assert mock_idx.call_count == 2
    called_names = {call[0][0].name for call in mock_idx.call_args_list}
    assert called_names == {"hyle", "notes"}
    assert "2 project(s) indexed" in result


def test_local_all_only_takes_precedence_over_skip():
    p1 = _make_project("hyle")
    p2 = _make_project("notes")
    p3 = _make_project("trivia")
    cfg = _make_config(projects=[p1, p2, p3])

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
        patch("recall.commands.ingest.index_project", return_value=5) as mock_idx,
    ):
        result = _run_local_ingest(mode="all", params={"only": ["hyle"], "skip": ["hyle"]})

    assert mock_idx.call_count == 1
    assert mock_idx.call_args[0][0].name == "hyle"


def test_local_skips_project_with_missing_path():
    existing = _make_project("ok", exists=True)
    missing = _make_project("gone", exists=False)
    cfg = _make_config(projects=[existing, missing])

    with (
        patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")),
        patch("recall.commands.ingest.load_config", return_value=cfg),
        patch("recall.commands.ingest.ensure_qdrant"),
        patch("recall.commands.ingest.index_project", return_value=7) as mock_idx,
    ):
        result = _run_local_ingest(mode="all", params={})

    assert mock_idx.call_count == 1
    assert "1 project(s) indexed" in result
