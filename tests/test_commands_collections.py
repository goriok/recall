from unittest.mock import patch
from pathlib import Path
from typer.testing import CliRunner
from recall.cli import app
from recall.config import Config, QdrantConfig, EmbeddingConfig
from recall.core.interfaces import Point
from tests.fakes import FakeVectorStore

runner = CliRunner()

FAKE_CONFIG = Config(qdrant=QdrantConfig(), embedding=EmbeddingConfig(), projects=[])


def _seeded_store(**collections: int) -> FakeVectorStore:
    store = FakeVectorStore()
    for name, points_count in collections.items():
        store.collections[name] = [
            Point(id=i, vector=[0.1], payload={}) for i in range(points_count)
        ]
    return store


def test_collections_list_empty():
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantVectorStore", return_value=FakeVectorStore()):
        result = runner.invoke(app, ["collections", "list"])

    assert result.exit_code == 0
    assert "No collections" in result.output


def test_collections_list_shows_collections():
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantVectorStore", return_value=_seeded_store(**{"my-project": 42})):
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
    store = _seeded_store(**{"my-project": 1})
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantVectorStore", return_value=store):
        result = runner.invoke(app, ["collections", "drop", "my-project", "--yes"])

    assert result.exit_code == 0
    assert "my-project" not in store.collections
    assert "my-project" in result.output


def test_collections_drop_all_with_yes():
    store = _seeded_store(**{"proj-a": 1, "proj-b": 1})
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantVectorStore", return_value=store):
        result = runner.invoke(app, ["collections", "drop", "--all", "--yes"])

    assert result.exit_code == 0
    assert store.collections == {}


from recall.meta import META_COLLECTION, read_meta, write_meta


def _invoke(store, args):
    with patch("recall.commands.collections.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.collections.load_config", return_value=FAKE_CONFIG), \
         patch("recall.commands.collections.ensure_qdrant"), \
         patch("recall.commands.collections.QdrantVectorStore", return_value=store):
        return runner.invoke(app, args)


def test_collections_list_hides_the_meta_collection():
    store = _seeded_store(docs=3)
    write_meta(store, "docs", "m", 4)

    result = _invoke(store, ["collections", "list"])

    assert "docs" in result.output
    assert META_COLLECTION not in result.output


def test_collections_drop_also_removes_the_collection_metadata():
    store = _seeded_store(a=1, b=1)
    write_meta(store, "a", "m", 4)
    write_meta(store, "b", "m", 4)

    result = _invoke(store, ["collections", "drop", "a", "--yes"])

    assert result.exit_code == 0
    assert "a" not in store.collections
    assert read_meta(store, "a") is None
    assert read_meta(store, "b") is not None


def test_collections_drop_all_clears_the_meta_collection_too():
    store = _seeded_store(a=1, b=1)
    write_meta(store, "a", "m", 4)

    result = _invoke(store, ["collections", "drop", "--all", "--yes"])

    assert result.exit_code == 0
    assert store.collections == {}


def test_collections_drop_all_does_not_count_the_meta_collection():
    store = FakeVectorStore()
    write_meta(store, "x", "m", 4)

    result = _invoke(store, ["collections", "drop", "--all", "--yes"])

    assert "No collections to drop" in result.output
