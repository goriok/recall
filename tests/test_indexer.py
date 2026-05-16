from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path

from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig
from recall.indexer import index_project


def _make_config() -> Config:
    return Config(qdrant=QdrantConfig(), embedding=EmbeddingConfig(), projects=[])


def test_index_project_skips_excluded_paths(tmp_path):
    """Files inside node_modules or other blocked dirs must not be indexed."""
    (tmp_path / "README.md").write_text("# Real doc\n\nContent.")
    node_mod = tmp_path / "node_modules" / "some-pkg"
    node_mod.mkdir(parents=True)
    (node_mod / "README.md").write_text("# Package readme")

    project = ProjectConfig(
        name="test",
        path=str(tmp_path),
        collection="test",
        path_exclude=["node_modules"],
    )

    with patch("recall.indexer.embed_batch", side_effect=lambda texts, **kw: [[0.1] * 768 for _ in texts]), \
         patch("recall.indexer.QdrantClient") as mock_qdrant, \
         patch("recall.indexer._collection_exists", return_value=True):
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client
        count = index_project(project, config=_make_config())

    assert count > 0
    all_sources = [
        pt.payload["source"]
        for call in mock_client.upsert.call_args_list
        for pt in call.kwargs["points"]
    ]
    assert not any("node_modules" in s for s in all_sources)


def test_index_project_skips_multiple_blocked_dirs(tmp_path):
    """Both .git and .venv dirs are filtered."""
    (tmp_path / "doc.md").write_text("# Doc\n\nReal content.")
    for blocked in [".git", ".venv"]:
        d = tmp_path / blocked
        d.mkdir()
        (d / "config.md").write_text("# internal")

    project = ProjectConfig(
        name="test",
        path=str(tmp_path),
        collection="test",
    )

    with patch("recall.indexer.embed_batch", side_effect=lambda texts, **kw: [[0.1] * 768 for _ in texts]), \
         patch("recall.indexer.QdrantClient") as mock_qdrant, \
         patch("recall.indexer._collection_exists", return_value=True):
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client
        count = index_project(project, config=_make_config())

    assert count > 0
    all_sources = [
        pt.payload["source"]
        for call in mock_client.upsert.call_args_list
        for pt in call.kwargs["points"]
    ]
    assert not any(".git" in s or ".venv" in s for s in all_sources)


def test_index_project_returns_zero_for_nonexistent_path():
    project = ProjectConfig(name="ghost", path="/nonexistent", collection="ghost")
    count = index_project(project, config=_make_config())
    assert count == 0
