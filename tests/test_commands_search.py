import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path
from recall.cli import app
from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig
from recall.searcher import SearchResult

runner = CliRunner()

FAKE_CONFIG = Config(
    qdrant=QdrantConfig(host="localhost", port=6333),
    embedding=EmbeddingConfig(model="nomic-embed-text", provider="ollama"),
    projects=[
        ProjectConfig(name="docs", path="/tmp/docs", collection="docs"),
    ],
)

FAKE_RESULTS = [
    SearchResult(
        text="## Streaming\n\nUse async generators for streaming responses.",
        source="docs/streaming.md",
        collection="docs",
        heading="Streaming",
        score=0.91,
    )
]


def test_search_command_exists():
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    assert "query" in result.output.lower()


def test_search_returns_results():
    with patch("recall.commands.search.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.search.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.search.semantic_search", return_value=FAKE_RESULTS):
        result = runner.invoke(app, ["search", "streaming"])

    assert result.exit_code == 0
    assert "Streaming" in result.output


def test_search_with_project_filter():
    with patch("recall.commands.search.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.search.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.search.semantic_search", return_value=FAKE_RESULTS) as mock_search:
        result = runner.invoke(app, ["search", "streaming", "--in", "docs"])

    assert result.exit_code == 0
    call_kwargs = mock_search.call_args[1]
    assert call_kwargs.get("collection") == "docs"


def test_search_with_min_score():
    with patch("recall.commands.search.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.search.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.search.semantic_search", return_value=FAKE_RESULTS) as mock_search:
        result = runner.invoke(app, ["search", "streaming", "--min-score", "0.7"])

    assert result.exit_code == 0
    call_kwargs = mock_search.call_args[1]
    assert call_kwargs.get("min_score") == 0.7


def test_search_shows_no_results_message():
    with patch("recall.commands.search.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.search.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.search.semantic_search", return_value=[]):
        result = runner.invoke(app, ["search", "nonexistent topic"])

    assert result.exit_code == 0
    assert "no results" in result.output.lower()
