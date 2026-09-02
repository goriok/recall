import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path
from recall.cli import app
from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig

runner = CliRunner()

FAKE_PROJECT = ProjectConfig(
    name="test-proj",
    path="/tmp/fake-docs",
    collection="test-proj",
    glob="**/*.md",
)

FAKE_CONFIG = Config(
    qdrant=QdrantConfig(host="localhost", port=6333),
    embedding=EmbeddingConfig(model="nomic-embed-text", provider="ollama"),
    projects=[FAKE_PROJECT],
)


def test_ingest_command_exists():
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output.lower()


def test_ingest_unknown_project_shows_error():
    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=FAKE_CONFIG):
        result = runner.invoke(app, ["ingest", "no-such-project"])
    assert result.exit_code != 0
    assert "no-such-project" in result.output


def test_ingest_calls_indexer_for_project(tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Hello\n\nContent here.\n")

    project = ProjectConfig(
        name="mypkg",
        path=str(tmp_path),
        collection="mypkg",
        glob="**/*.md",
    )
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "qdrant")),
        embedding=EmbeddingConfig(),
        projects=[project],
    )

    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=config), \
         patch("recall.commands.ingest.index_project") as mock_index:
        result = runner.invoke(app, ["ingest", "mypkg"])

    assert result.exit_code == 0
    mock_index.assert_called_once()
    call_args = mock_index.call_args
    assert call_args[0][0] == project


def test_ingest_skips_missing_path(tmp_path):
    project = ProjectConfig(
        name="ghost",
        path="/nonexistent/path",
        collection="ghost",
    )
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "qdrant")),
        embedding=EmbeddingConfig(),
        projects=[project],
    )

    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=config), \
         patch("recall.commands.ingest.index_project") as mock_index:
        result = runner.invoke(app, ["ingest", "--all"])

    assert result.exit_code == 0
    mock_index.assert_not_called()
    assert "skipping" in result.output


def test_ingest_all_calls_indexer_for_each_project(tmp_path):
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "qdrant")),
        embedding=EmbeddingConfig(),
        projects=[
            ProjectConfig(name="a", path=str(tmp_path), collection="a"),
            ProjectConfig(name="b", path=str(tmp_path), collection="b"),
        ],
    )

    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=config), \
         patch("recall.commands.ingest.index_project") as mock_index:
        result = runner.invoke(app, ["ingest", "--all"])

    assert result.exit_code == 0
    assert mock_index.call_count == 2
