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
