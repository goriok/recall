from __future__ import annotations

from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig
from recall.indexer import index_project
from tests.fakes import FakeEmbeddingProvider, FakeVectorStore


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

    vector_store = FakeVectorStore()
    count = index_project(
        project,
        config=_make_config(),
        vector_store=vector_store,
        embedding_provider=FakeEmbeddingProvider(),
    )

    assert count > 0
    all_sources = [p.payload["source"] for p in vector_store.collections["test"]]
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

    vector_store = FakeVectorStore()
    count = index_project(
        project,
        config=_make_config(),
        vector_store=vector_store,
        embedding_provider=FakeEmbeddingProvider(),
    )

    assert count > 0
    all_sources = [p.payload["source"] for p in vector_store.collections["test"]]
    assert not any(".git" in s or ".venv" in s for s in all_sources)


def test_index_project_returns_zero_for_nonexistent_path():
    project = ProjectConfig(name="ghost", path="/nonexistent", collection="ghost")
    count = index_project(
        project,
        config=_make_config(),
        vector_store=FakeVectorStore(),
        embedding_provider=FakeEmbeddingProvider(),
    )
    assert count == 0


def test_index_project_stores_absolute_source_path(tmp_path):
    """source in payload must be the absolute file path, not relative."""
    (tmp_path / "guide.md").write_text("# Guide\n\nContent here.")

    project = ProjectConfig(
        name="test",
        path=str(tmp_path),
        collection="test",
    )

    vector_store = FakeVectorStore()
    index_project(
        project,
        config=_make_config(),
        vector_store=vector_store,
        embedding_provider=FakeEmbeddingProvider(),
    )

    all_sources = [p.payload["source"] for p in vector_store.collections["test"]]
    expected = str(tmp_path / "guide.md")
    assert any(s == expected for s in all_sources)
