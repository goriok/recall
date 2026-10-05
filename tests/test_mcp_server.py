import pytest
from unittest.mock import patch
from pathlib import Path
from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig
from recall.searcher import SearchResult
from tests.fakes import FakeEmbeddingProvider, FakeVectorStore

FAKE_CONFIG = Config(
    qdrant=QdrantConfig(),
    embedding=EmbeddingConfig(),
    projects=[ProjectConfig(name="docs", path="/tmp/docs", collection="docs")],
)

FAKE_RESULTS = [
    SearchResult(
        text="## Streaming\n\nUse async generators.",
        source="docs/streaming.md",
        collection="docs",
        heading="Streaming",
        score=0.92,
    )
]


@pytest.fixture(autouse=True)
def _reset_adapter_singleton():
    """mcp_server caches the vector store/embedding provider per process — reset
    between tests so one test's fake adapters don't leak into the next."""
    import recall.mcp_server as mcp_server

    yield
    mcp_server._vector_store = None
    mcp_server._embedding_provider = None


def _patch_adapters():
    return patch(
        "recall.mcp_server._get_adapters",
        return_value=(FakeVectorStore(), FakeEmbeddingProvider()),
    )


def test_search_knowledge_returns_formatted_text():
    from recall.mcp_server import search_knowledge

    with patch("recall.mcp_server.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.mcp_server.load_config", return_value=FAKE_CONFIG), \
         _patch_adapters(), \
         patch("recall.mcp_server.semantic_search", return_value=FAKE_RESULTS):
        result = search_knowledge("streaming")

    assert "Streaming" in result
    assert "docs/streaming.md" in result
    assert "0.92" in result


def test_search_knowledge_with_project_filter():
    from recall.mcp_server import search_knowledge

    with patch("recall.mcp_server.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.mcp_server.load_config", return_value=FAKE_CONFIG), \
         _patch_adapters(), \
         patch("recall.mcp_server.semantic_search", return_value=FAKE_RESULTS) as mock_search:
        search_knowledge("streaming", project="docs")

    call_kwargs = mock_search.call_args[1]
    assert call_kwargs.get("collection") == "docs"


def test_search_knowledge_returns_no_results_message():
    from recall.mcp_server import search_knowledge

    with patch("recall.mcp_server.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.mcp_server.load_config", return_value=FAKE_CONFIG), \
         _patch_adapters(), \
         patch("recall.mcp_server.semantic_search", return_value=[]):
        result = search_knowledge("nothing here")

    assert "no results" in result.lower()


from recall.config import RepoConfig
from recall.core.interfaces import Point
from recall.meta import write_meta

CODE_CONFIG = Config(
    qdrant=QdrantConfig(),
    embedding=EmbeddingConfig(),
    projects=[ProjectConfig(name="docs", path="/tmp/docs", collection="docs")],
    repos=[RepoConfig(name="svc", root="/tmp/svc")],
)


def _code_store():
    store = FakeVectorStore()
    store.recreate_collection("code.svc", 4)
    store.upsert(
        "code.svc",
        [
            Point(
                id=1, vector=[0.1],
                payload={
                    "text": "def authenticate(): ...", "file_path": "src/auth.py", "repo_name": "svc",
                    "start_line": 45, "end_line": 88, "symbol_name": "authenticate", "kind": "function",
                    "community_name": "auth", "is_god_node": True, "related_symbols": ["verify_token"],
                },
            )
        ],
    )
    return store


def _with_config(config, store, fn):
    with patch("recall.mcp_server.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.mcp_server.load_config", return_value=config), \
         patch("recall.mcp_server._get_adapters", return_value=(store, FakeEmbeddingProvider())):
        return fn()


def test_search_code_returns_location_and_graph_context():
    from recall.mcp_server import search_code_knowledge

    result = _with_config(CODE_CONFIG, _code_store(), lambda: search_code_knowledge("auth"))

    assert "src/auth.py:45-88" in result
    assert "repo: svc" in result
    assert "symbol: authenticate" in result
    assert "community: auth" in result
    assert "god_node: true" in result
    assert "related: verify_token" in result
    assert "def authenticate" in result


def test_search_code_without_configured_repos_explains_how_to_add_one():
    from recall.mcp_server import search_code_knowledge

    result = _with_config(FAKE_CONFIG, FakeVectorStore(), lambda: search_code_knowledge("x"))

    assert "[[repos]]" in result


def test_search_code_no_results_message():
    from recall.mcp_server import search_code_knowledge

    result = _with_config(CODE_CONFIG, FakeVectorStore(), lambda: search_code_knowledge("x", repo="svc"))

    assert "no results" in result.lower()


def test_search_code_reports_model_mismatch_as_text():
    from recall.mcp_server import search_code_knowledge

    store = _code_store()
    write_meta(store, "code.svc", "openai:other", 4)

    result = _with_config(CODE_CONFIG, store, lambda: search_code_knowledge("x"))

    assert "--recreate" in result


def test_search_docs_refuses_code_collections():
    from recall.mcp_server import search_knowledge

    for name in ("code.svc", "svc"):
        result = _with_config(CODE_CONFIG, _code_store(), lambda: search_knowledge("x", project=name))
        assert "search_code" in result


def test_search_docs_reports_mixed_model_error_as_text():
    from recall.mcp_server import search_knowledge

    remote = EmbeddingConfig(provider="openai", model="m", base_url="u", api_key_env="K")
    config = Config(
        projects=[
            ProjectConfig(name="a", path="/a", collection="a"),
            ProjectConfig(name="b", path="/b", collection="b", embedding=remote),
        ]
    )
    from recall.embeddings import ProviderResolver

    resolver = ProviderResolver(config, factory=lambda c: FakeEmbeddingProvider(model_id=f"{c.provider}:{c.model}"))
    with patch("recall.mcp_server.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.mcp_server.load_config", return_value=config), \
         patch("recall.mcp_server._get_adapters", return_value=(FakeVectorStore(), resolver)):
        result = search_knowledge("x")

    assert "different embedding models" in result


def test_search_results_without_file_path_keep_the_legacy_format():
    from recall.mcp_server import _format

    text = _format(FAKE_RESULTS)

    assert text.startswith("### [docs] docs/streaming.md (score: 0.92)")


def test_search_results_with_file_path_show_section_breadcrumb():
    from recall.mcp_server import _format

    result = SearchResult(
        text="body", source="/abs/x.md", collection="c", heading="B", score=0.5,
        file_path="topics/x.md", start_line=3, end_line=9, breadcrumb=["A", "B"],
    )

    text = _format([result])

    assert "### [c] topics/x.md:3-9 (score: 0.50)" in text
    assert "section: A > B" in text
    assert "/abs/x.md" not in text


def test_explain_architecture_returns_report_and_god_nodes():
    from recall.mcp_server import explain_architecture_text

    store = FakeVectorStore()
    write_meta(store, "code.svc", "m", 4, report="# Report body", god_nodes=["Service", "load_config"])

    result = _with_config(CODE_CONFIG, store, lambda: explain_architecture_text("svc"))

    assert "# Architecture of svc" in result
    assert "- Service" in result and "- load_config" in result
    assert "# Report body" in result


def test_explain_architecture_unknown_repo_lists_configured_ones():
    from recall.mcp_server import explain_architecture_text

    result = _with_config(CODE_CONFIG, FakeVectorStore(), lambda: explain_architecture_text("ghost"))

    assert "Unknown repo 'ghost'" in result and "svc" in result


def test_explain_architecture_without_report_says_how_to_generate_it():
    from recall.mcp_server import explain_architecture_text

    store = FakeVectorStore()
    write_meta(store, "code.svc", "m", 4)

    result = _with_config(CODE_CONFIG, store, lambda: explain_architecture_text("svc"))

    assert "recall ingest svc" in result


def test_explain_architecture_only_reads_the_requested_repo():
    from recall.mcp_server import explain_architecture_text

    config = Config(repos=[RepoConfig(name="a", root="/a"), RepoConfig(name="b", root="/b")])
    store = FakeVectorStore()
    write_meta(store, "code.a", "m", 4, report="REPORT-A")
    write_meta(store, "code.b", "m", 4, report="REPORT-B")

    result = _with_config(config, store, lambda: explain_architecture_text("a"))

    assert "REPORT-A" in result and "REPORT-B" not in result


def test_tools_are_registered_under_their_public_names():
    import asyncio

    from recall.mcp_server import mcp

    names = {tool.name for tool in asyncio.run(mcp.list_tools())}

    assert {"search_docs", "search_code", "explain_architecture"} <= names


def test_tool_wrappers_delegate_to_core_functions():
    from recall import mcp_server

    with patch.object(mcp_server, "search_knowledge", return_value="docs") as docs, \
         patch.object(mcp_server, "search_code_knowledge", return_value="code") as code, \
         patch.object(mcp_server, "explain_architecture_text", return_value="arch") as arch:
        assert mcp_server.search_docs("q", project="p", top_k=2, min_score=0.5) == "docs"
        assert mcp_server.search_code_mcp("q", repo="r", top_k=3) == "code"
        assert mcp_server.explain_architecture("r") == "arch"

    docs.assert_called_once_with("q", project="p", top_k=2, min_score=0.5)
    code.assert_called_once_with("q", repo="r", top_k=3, min_score=None)
    arch.assert_called_once_with("r")


def test_get_adapters_builds_store_and_resolver_once_and_ensures_remote_qdrant():
    from recall import mcp_server

    config = Config(qdrant=QdrantConfig(host="localhost", port=6333), embedding=EmbeddingConfig())
    with patch("recall.mcp_server.QdrantVectorStore") as store_cls, \
         patch("recall.mcp_server.ensure_qdrant") as ensure:
        first = mcp_server._get_adapters(config)
        second = mcp_server._get_adapters(config)

    assert first[0] is second[0] and first[1] is second[1]
    store_cls.assert_called_once()
    ensure.assert_called_once_with("http://localhost:6333", None)


from recall.adapters.openai_embedding_provider import EmbeddingProviderError
from recall.embeddings import as_resolver


def _sources_text(config, store, resolver=None):
    resolver = resolver or as_resolver(FakeEmbeddingProvider())
    with patch("recall.mcp_server.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.mcp_server.load_config", return_value=config), \
         patch("recall.mcp_server._get_adapters", return_value=(store, resolver)):
        from recall.mcp_server import list_sources_text

        return list_sources_text()


def test_list_sources_without_configuration_explains_what_to_add():
    assert "[[repos]]" in _sources_text(Config(), FakeVectorStore())


def test_list_sources_reports_not_indexed_projects_with_the_ingest_command():
    text = _sources_text(CODE_CONFIG, FakeVectorStore())
    assert "docs (docs, repo docs): not indexed yet — run `recall ingest docs`" in text
    assert "code.svc (code, repo svc): not indexed yet — run `recall ingest svc`" in text


def test_list_sources_shows_points_model_files_and_last_ingest():
    store = _code_store()
    write_meta(store, "code.svc", "ollama:nomic-embed-text", 768, files=12, indexed_at="2026-10-05T10:00:00+00:00")

    text = _sources_text(CODE_CONFIG, store)

    line = next(l for l in text.splitlines() if l.startswith("- code.svc"))
    assert "1 points" in line and "model ollama:nomic-embed-text" in line
    assert "12 files" in line and "indexed 2026-10-05T10:00:00+00:00" in line
    assert "MISMATCH" not in line


def test_list_sources_flags_a_model_mismatch_with_the_fix():
    store = _code_store()
    write_meta(store, "code.svc", "openai:nomic-embed-text-v1-5", 768, indexed_at="2026-10-05T10:00:00+00:00")

    line = next(l for l in _sources_text(CODE_CONFIG, store).splitlines() if l.startswith("- code.svc"))

    assert "MODEL MISMATCH (configured ollama:nomic-embed-text)" in line
    assert "recall ingest svc --recreate" in line


def test_list_sources_marks_legacy_collections_without_a_record():
    store = FakeVectorStore()
    store.recreate_collection("docs", 768)

    line = next(l for l in _sources_text(CODE_CONFIG, store).splitlines() if l.startswith("- docs"))

    assert "legacy, no record" in line and "indexed at unknown time" in line


def test_list_sources_survives_an_unavailable_embedding_provider():
    class Broken:
        def for_project(self, project):
            raise EmbeddingProviderError("environment variable RECALL_EMBEDDING_API_KEY is not set")

    store = _code_store()
    write_meta(store, "code.svc", "openai:m", 4, indexed_at="2026-10-05T10:00:00+00:00")

    text = _sources_text(CODE_CONFIG, store, Broken())

    assert "embedding provider unavailable: environment variable RECALL_EMBEDDING_API_KEY is not set" in text
    assert "code.svc" in text


def test_list_sources_never_exposes_absolute_paths():
    text = _sources_text(CODE_CONFIG, _code_store())
    assert "/tmp/svc" not in text and "/tmp/docs" not in text


def test_list_sources_tool_wrapper_and_registration():
    import asyncio

    from recall import mcp_server

    with patch.object(mcp_server, "list_sources_text", return_value="listing"):
        assert mcp_server.list_sources() == "listing"
    assert "list_sources" in {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
