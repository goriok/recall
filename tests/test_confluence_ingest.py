import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from typer.testing import CliRunner
from recall.cli import app
from recall.config import Config, QdrantConfig, EmbeddingConfig
from recall.confluence.client import ConfluenceConfig, ConfluencePage

runner = CliRunner()

FAKE_CONFIG = Config(
    qdrant=QdrantConfig(),
    embedding=EmbeddingConfig(),
    projects=[],
)

FAKE_CONFLUENCE_CFG = ConfluenceConfig(
    url="https://org.atlassian.net",
    auth_type="token",
    email="user@org.com",
    token="secret",
)

FAKE_PAGES = [
    ConfluencePage(
        id="1",
        title="Architecture Overview",
        space_key="ENG",
        html_body="<h1>Overview</h1><p>Content here.</p>",
        url="https://org.atlassian.net/wiki/spaces/ENG/pages/1",
        version=1,
    )
]


def test_ingest_confluence_command_exists():
    result = runner.invoke(app, ["ingest-confluence", "--help"])
    assert result.exit_code == 0


def test_ingest_confluence_requires_at_least_one_flag():
    with patch("recall.commands.ingest_confluence.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest_confluence.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.ingest_confluence.load_confluence_config", return_value=FAKE_CONFLUENCE_CFG):
        result = runner.invoke(app, ["ingest-confluence"])
    assert result.exit_code != 0
    assert "space" in result.output.lower() or "page" in result.output.lower() or "label" in result.output.lower()


def test_ingest_confluence_space_calls_indexer():
    with patch("recall.commands.ingest_confluence.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest_confluence.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.ingest_confluence.load_confluence_config", return_value=FAKE_CONFLUENCE_CFG), \
         patch("recall.commands.ingest_confluence.ensure_qdrant"), \
         patch("recall.commands.ingest_confluence.ConfluenceClient") as mock_client_cls, \
         patch("recall.commands.ingest_confluence.index_confluence_pages") as mock_index:
        mock_client_cls.return_value.get_space_pages.return_value = FAKE_PAGES
        mock_index.return_value = 5
        result = runner.invoke(app, ["ingest-confluence", "--space", "ENG"])

    assert result.exit_code == 0
    mock_index.assert_called_once()


def test_ingest_confluence_page_id_calls_indexer():
    with patch("recall.commands.ingest_confluence.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest_confluence.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.ingest_confluence.load_confluence_config", return_value=FAKE_CONFLUENCE_CFG), \
         patch("recall.commands.ingest_confluence.ensure_qdrant"), \
         patch("recall.commands.ingest_confluence.ConfluenceClient") as mock_client_cls, \
         patch("recall.commands.ingest_confluence.index_confluence_pages") as mock_index:
        mock_client_cls.return_value.get_page.return_value = FAKE_PAGES[0]
        mock_client_cls.return_value.get_children.return_value = []
        mock_index.return_value = 3
        result = runner.invoke(app, ["ingest-confluence", "--page-id", "123456"])

    assert result.exit_code == 0
    mock_index.assert_called_once()


def test_index_confluence_pages_chunks_and_upserts(tmp_path):
    from recall.confluence.indexer import index_confluence_pages

    with patch("recall.confluence.indexer.embed_batch", side_effect=lambda texts, config: [[0.1] * 768 for _ in texts]), \
         patch("recall.confluence.indexer.QdrantClient") as mock_qdrant, \
         patch("recall.confluence.indexer._collection_exists", return_value=False):
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client

        cfg = Config(qdrant=QdrantConfig(), embedding=EmbeddingConfig(), projects=[])
        count = index_confluence_pages(FAKE_PAGES, collection="confluence-eng", config=cfg)

    assert count > 0
    mock_client.upsert.assert_called_once()
