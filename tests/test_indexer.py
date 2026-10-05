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


import re

import pytest

from recall.discovery import DiscoveryError
from recall.indexer import IndexReport
from recall.meta import ModelMismatchError, read_meta
from recall.core.interfaces import Point
from recall.graphify_adapter import parse_graph


def _project(tmp_path, **kwargs):
    return ProjectConfig(name="repo.topic", path=str(tmp_path), collection="repo.topic", **kwargs)


def _index(project, store, provider=None, **kwargs):
    return index_project(
        project,
        config=_make_config(),
        vector_store=store,
        embedding_provider=provider or FakeEmbeddingProvider(),
        **kwargs,
    )


def _payloads(store, name="repo.topic"):
    return [p.payload for p in store.collections[name]]


def test_markdown_payload_has_relative_file_path_lines_and_breadcrumb(tmp_path):
    topics = tmp_path / "topics" / "auth"
    topics.mkdir(parents=True)
    (topics / "guide.md").write_text("# Guide\n\nintro\n\n## Setup\n\nsteps\n")
    project = ProjectConfig(
        name="r.auth", path=str(topics), collection="r.auth", repo_root=str(tmp_path), repo_name="myrepo"
    )
    store = FakeVectorStore()

    _index(project, store)

    payload = next(p for p in _payloads(store, "r.auth") if p["heading"] == "Setup")
    assert payload["file_path"] == "topics/auth/guide.md"
    assert not payload["file_path"].startswith("/")
    assert payload["repo_name"] == "myrepo"
    assert payload["breadcrumb"] == ["Guide", "Setup"]
    assert (payload["start_line"], payload["end_line"]) == (5, 7)
    assert payload["source"] == str((topics / "guide.md").resolve())


def test_reingest_without_changes_keeps_ids_and_count(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\none\n\n# B\n\ntwo\n")
    store = FakeVectorStore()
    project = _project(tmp_path)

    _index(project, store)
    first = sorted(p.id for p in store.collections["repo.topic"])
    _index(project, store)

    assert sorted(p.id for p in store.collections["repo.topic"]) == first


def test_reingest_replaces_chunks_of_a_changed_file(tmp_path):
    doc = tmp_path / "a.md"
    doc.write_text("# A\n\nold text\n")
    store = FakeVectorStore()
    project = _project(tmp_path)
    _index(project, store)

    doc.write_text("# A\n\nnew text\n\n# C\n\nextra\n")
    _index(project, store)

    texts = " ".join(p["text"] for p in _payloads(store))
    assert "old text" not in texts and "new text" in texts
    assert store.count("repo.topic") == 2


def test_reingest_removes_points_of_deleted_files(tmp_path):
    (tmp_path / "keep.md").write_text("# K\n\nkeep\n")
    gone = tmp_path / "gone.md"
    gone.write_text("# G\n\ngone\n")
    store = FakeVectorStore()
    project = _project(tmp_path)
    _index(project, store)

    gone.unlink()
    report = IndexReport()
    _index(project, store, report=report)

    assert {p["file_path"] for p in _payloads(store)} == {"keep.md"}
    assert report.removed_files == 1


def test_embedding_failure_does_not_delete_existing_points(tmp_path):
    doc = tmp_path / "a.md"
    doc.write_text("# A\n\nstable\n")
    store = FakeVectorStore()
    project = _project(tmp_path)
    _index(project, store)

    class Boom(FakeEmbeddingProvider):
        def embed_batch(self, texts):
            raise RuntimeError("endpoint down")

    doc.write_text("# A\n\nchanged\n")
    with pytest.raises(RuntimeError):
        _index(project, store, Boom())

    assert "stable" in " ".join(p["text"] for p in _payloads(store))


def test_meta_records_model_and_dimensions(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    store = FakeVectorStore()

    _index(_project(tmp_path), store, FakeEmbeddingProvider(dim=4, model_id="openai:m"))

    meta = read_meta(store, "repo.topic")
    assert meta["model_id"] == "openai:m" and meta["dimensions"] == 4


def test_collection_vector_size_follows_provider_dimensions(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    sizes = {}

    class Store(FakeVectorStore):
        def recreate_collection(self, name, vector_size):
            sizes[name] = vector_size
            super().recreate_collection(name, vector_size)

    _index(_project(tmp_path), Store(), FakeEmbeddingProvider(dim=1024))

    assert sizes["repo.topic"] == 1024


def test_changing_embedding_model_requires_recreate(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    store = FakeVectorStore()
    project = _project(tmp_path)
    _index(project, store, FakeEmbeddingProvider(model_id="openai:m", dim=4))

    with pytest.raises(ModelMismatchError):
        _index(project, store, FakeEmbeddingProvider(model_id="ollama:other", dim=4))

    _index(project, store, FakeEmbeddingProvider(model_id="ollama:other", dim=4), recreate=True)
    assert read_meta(store, "repo.topic")["model_id"] == "ollama:other"


def test_legacy_collection_without_meta_is_rebuilt(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    store = FakeVectorStore()
    store.recreate_collection("repo.topic", 768)
    store.upsert("repo.topic", [Point(id=1, vector=[0.1], payload={"text": "old", "source": "/x.md"})])
    report = IndexReport()

    _index(_project(tmp_path), store, report=report)

    assert all(p["text"] != "old" for p in _payloads(store))
    assert any("legacy" in w for w in report.warnings)


def test_oversized_chunk_limit_warns_for_small_input_providers(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    report = IndexReport()

    _index(_project(tmp_path, max_chunk_chars=4000), FakeVectorStore(), FakeEmbeddingProvider(max_input_chars=1500), report=report)

    assert any("exceeds" in w for w in report.warnings)


def test_max_chunk_chars_splits_large_sections_before_embedding(tmp_path):
    big = "\n\n".join("para " * 30 for _ in range(10))
    (tmp_path / "a.md").write_text(f"# Big\n\n{big}\n")
    provider = FakeEmbeddingProvider()

    _index(_project(tmp_path, max_chunk_chars=400), FakeVectorStore(), provider)

    assert max(len(t) for batch in provider.calls for t in batch) <= 420


def test_report_counts_files_and_skips(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    (tmp_path / "big.md").write_text("x" * 200)
    report = IndexReport()

    count = _index(_project(tmp_path, max_file_bytes=100), FakeVectorStore(), report=report)

    assert report.files == 1 and report.chunks == count == 1
    assert report.skipped["too_large"] == 1


def test_unreadable_file_is_skipped_and_reported(tmp_path):
    (tmp_path / "ok.md").write_text("# A\n\nbody\n")
    (tmp_path / "latin.md").write_bytes("# T\n\nação".encode("latin-1"))
    report = IndexReport()

    _index(_project(tmp_path), FakeVectorStore(), report=report)

    assert report.skipped["unreadable"] == 1 and report.files == 1


def test_directory_without_matching_files_raises(tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(DiscoveryError):
        _index(_project(tmp_path), FakeVectorStore())


def test_point_count_warning(tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    monkeypatch.setattr("recall.indexer.POINT_WARNING", 0)
    report = IndexReport()
    _index(_project(tmp_path), FakeVectorStore(), report=report)
    assert any("Qdrant server" in w for w in report.warnings)


GRAPH = {
    "nodes": [
        {"id": "mod", "label": "mod.py", "source_file": "mod.py", "source_location": "L1", "community": 1, "community_name": "core"},
        {"id": "cls", "label": "Service", "source_file": "mod.py", "source_location": "L4", "community": 1, "community_name": "core"},
        {"id": "run", "label": ".run()", "source_file": "mod.py", "source_location": "L7", "community": 1, "community_name": "core"},
        {"id": "helper", "label": "helper()", "source_file": "mod.py", "source_location": "L11", "community": 1, "community_name": "core"},
    ],
    "links": [
        {"source": "cls", "target": "run", "relation": "method", "confidence": "EXTRACTED"},
        {"source": "run", "target": "helper", "relation": "calls", "confidence": "EXTRACTED"},
    ],
}

CODE = '''import os


class Service:
    """doc"""

    def run(self):
        return helper()


def helper():
    return 1
'''


def _repo(tmp_path, **kwargs):
    (tmp_path / "mod.py").write_text(CODE)
    (tmp_path / "README.md").write_text("# Repo\n\nabout\n\n## Usage\n\nrun it\n")
    return ProjectConfig(
        name="myrepo", path=str(tmp_path), collection="code.myrepo", kind="code",
        repo_name="myrepo", repo_root=str(tmp_path), globs=["**/*.py", "**/*.md"], **kwargs,
    )


def test_code_repo_indexes_symbols_with_graph_metadata(tmp_path, monkeypatch):
    graph = parse_graph(GRAPH, {"cls"}, "# Graph report", tmp_path.resolve())
    monkeypatch.setattr("recall.indexer.build_graph", lambda *a, **k: graph)
    store = FakeVectorStore()
    report = IndexReport()

    _index(_repo(tmp_path), store, report=report)

    payloads = {p["symbol_name"]: p for p in _payloads(store, "code.myrepo") if p.get("kind") != "markdown"}
    run = payloads["Service.run"]
    assert run["file_path"] == "mod.py"
    assert (run["start_line"], run["end_line"]) == (7, 8)
    assert run["community_name"] == "core"
    assert run["related_symbols"] == ["helper"]
    assert payloads["Service"]["is_god_node"] is True
    assert report.graph is True
    meta = read_meta(store, "code.myrepo")
    assert meta["report"] == "# Graph report" and meta["god_nodes"] == ["Service"]


def test_code_repo_routes_markdown_files_through_markdown_chunker(tmp_path, monkeypatch):
    monkeypatch.setattr("recall.indexer.build_graph", lambda *a, **k: None)
    store = FakeVectorStore()

    _index(_repo(tmp_path), store)

    readme = [p for p in _payloads(store, "code.myrepo") if p["file_path"] == "README.md"]
    assert {p["kind"] for p in readme} == {"markdown"}
    assert any(p["breadcrumb"] == ["Repo", "Usage"] for p in readme)


def test_code_repo_without_graphify_still_indexes_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("recall.indexer.build_graph", lambda *a, **k: None)
    store = FakeVectorStore()
    report = IndexReport()

    _index(_repo(tmp_path), store, report=report)

    code = [p for p in _payloads(store, "code.myrepo") if p["kind"] != "markdown"]
    assert code and all(p["community_name"] == "" and p["related_symbols"] == [] for p in code)
    assert report.graph is False
    assert "report" not in read_meta(store, "code.myrepo")


def test_code_repo_graph_can_be_disabled(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr("recall.indexer.build_graph", lambda *a, **k: called.append(1))
    project = _repo(tmp_path)
    project.graphify.enabled = False

    _index(project, FakeVectorStore())

    assert called == []


def test_code_reingest_keeps_neighbor_ids_when_a_function_is_inserted(tmp_path, monkeypatch):
    monkeypatch.setattr("recall.indexer.build_graph", lambda *a, **k: None)
    store = FakeVectorStore()
    project = _repo(tmp_path)
    _index(project, store)
    ids = {p.payload["symbol_name"]: p.id for p in store.collections["code.myrepo"] if p.payload.get("symbol_name")}

    (tmp_path / "mod.py").write_text("def added():\n    pass\n\n\n" + CODE)
    _index(project, store)

    after = {p.payload["symbol_name"]: p.id for p in store.collections["code.myrepo"] if p.payload.get("symbol_name")}
    assert after["Service.run"] == ids["Service.run"]
    assert after["helper"] == ids["helper"]
    assert "added" in after


def test_meta_records_file_count_and_ingest_time(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n")
    (tmp_path / "b.md").write_text("# B\n\nbody\n")
    store = FakeVectorStore()

    _index(_project(tmp_path), store)

    meta = read_meta(store, "repo.topic")
    assert meta["files"] == 2
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", meta["indexed_at"])
