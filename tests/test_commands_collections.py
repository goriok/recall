from unittest.mock import patch, MagicMock
from pathlib import Path
from typer.testing import CliRunner
from recall.cli import app
from recall.config import Config, QdrantConfig, EmbeddingConfig

runner = CliRunner()

FAKE_CONFIG = Config(qdrant=QdrantConfig(), embedding=EmbeddingConfig(), projects=[])


def _mock_collection(name: str, points_count: int = 10):
    col = MagicMock()
    col.name = name
    info = MagicMock()
    info.points_count = points_count
    return col, info


def test_collections_list_empty():
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantClient") as mock_qdrant:
        mock_qdrant.return_value.get_collections.return_value.collections = []
        result = runner.invoke(app, ["collections", "list"])

    assert result.exit_code == 0
    assert "No collections" in result.output


def test_collections_list_shows_collections():
    col, info = _mock_collection("my-project", 42)
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantClient") as mock_qdrant:
        mock_qdrant.return_value.get_collections.return_value.collections = [col]
        mock_qdrant.return_value.get_collection.return_value = info
        result = runner.invoke(app, ["collections", "list"])

    assert result.exit_code == 0
    assert "my-project" in result.output
    assert "42" in result.output


def test_collections_drop_requires_name_or_all():
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"):
        result = runner.invoke(app, ["collections", "drop"])

    assert result.exit_code != 0


def test_collections_drop_single_with_yes():
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantClient") as mock_qdrant:
        result = runner.invoke(app, ["collections", "drop", "my-project", "--yes"])

    assert result.exit_code == 0
    mock_qdrant.return_value.delete_collection.assert_called_once_with("my-project")
    assert "my-project" in result.output


def test_collections_drop_all_with_yes():
    col1, _ = _mock_collection("proj-a")
    col2, _ = _mock_collection("proj-b")
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantClient") as mock_qdrant:
        mock_qdrant.return_value.get_collections.return_value.collections = [col1, col2]
        result = runner.invoke(app, ["collections", "drop", "--all", "--yes"])

    assert result.exit_code == 0
    assert mock_qdrant.return_value.delete_collection.call_count == 2
