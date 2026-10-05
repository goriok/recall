from __future__ import annotations

from unittest.mock import MagicMock, patch

from qdrant_client import QdrantClient

from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.config import QdrantConfig
from recall.core.interfaces import Point


def _store() -> QdrantVectorStore:
    return QdrantVectorStore(QdrantConfig(), client=QdrantClient(":memory:"))


def _point(pid, path, vector=None):
    return Point(id=pid, vector=vector or [1.0, 0.0], payload={"file_path": path, "text": f"t{pid}"})


def test_collection_lifecycle():
    store = _store()
    assert not store.collection_exists("c")
    store.recreate_collection("c", 2)
    assert store.collection_exists("c")
    assert [c.name for c in store.list_collections()] == ["c"]
    store.delete_collection("c")
    assert not store.collection_exists("c")


def test_upsert_query_and_count():
    store = _store()
    store.recreate_collection("c", 2)
    store.upsert("c", [_point(1, "a.py"), _point(2, "b.py", [0.0, 1.0])])

    hits = store.query("c", [1.0, 0.0], 5)

    assert store.count("c") == 2
    assert hits[0].payload["file_path"] == "a.py"
    assert store.query("c", [1.0, 0.0], 5, min_score=0.99)[0].payload["file_path"] == "a.py"
    assert store.query("missing", [1.0, 0.0], 5) == []


def test_upsert_accepts_string_ids_and_replaces_by_id():
    store = _store()
    store.recreate_collection("c", 2)
    pid = "8c0b6c9a-0c1d-5c41-9d7b-0c5a3c1d2e3f"
    store.upsert("c", [Point(id=pid, vector=[1.0, 0.0], payload={"v": 1})])
    store.upsert("c", [Point(id=pid, vector=[1.0, 0.0], payload={"v": 2})])

    assert store.count("c") == 1
    assert store.scroll_where("c", "v", 2) == [{"v": 2}]


def test_delete_where_removes_matching_points():
    store = _store()
    store.recreate_collection("c", 2)
    store.upsert("c", [_point(1, "a.py"), _point(2, "b.py"), _point(3, "c.py")])

    store.delete_where("c", "file_path", ["a.py", "c.py"])

    assert store.distinct_values("c", "file_path") == {"b.py"}


def test_delete_where_batches_large_value_lists():
    store = _store()
    store.recreate_collection("c", 2)
    store.upsert("c", [_point(i, f"f{i}.py") for i in range(1, 6)])

    store.delete_where("c", "file_path", [f"f{i}.py" for i in range(1, 1200)])

    assert store.count("c") == 0


def test_distinct_values_returns_every_file_beyond_default_facet_limit():
    store = _store()
    store.recreate_collection("c", 2)
    store.upsert("c", [_point(i, f"file{i}.py") for i in range(1, 31)])

    assert len(store.distinct_values("c", "file_path")) == 30


def test_distinct_values_falls_back_to_scroll_when_facet_fails():
    store = _store()
    store.recreate_collection("c", 2)
    store.upsert("c", [_point(i, f"file{i}.py") for i in range(1, 600)])

    with patch.object(store._client, "facet", side_effect=RuntimeError("needs index")):
        assert len(store.distinct_values("c", "file_path")) == 599


def test_distinct_values_falls_back_to_scroll_when_facet_hits_limit():
    store = _store()
    store.recreate_collection("c", 2)
    store.upsert("c", [_point(1, "a.py"), _point(2, "b.py")])

    with patch("recall.adapters.qdrant_vector_store._FACET_LIMIT", 2):
        assert store.distinct_values("c", "file_path") == {"a.py", "b.py"}


def test_scroll_where_returns_payloads_and_empty_for_missing_collection():
    store = _store()
    store.recreate_collection("c", 2)
    store.upsert("c", [_point(1, "a.py")])

    assert store.scroll_where("c", "file_path", "a.py")[0]["text"] == "t1"
    assert store.scroll_where("c", "file_path", "nope") == []
    assert store.scroll_where("ghost", "file_path", "a.py") == []


def test_server_mode_builds_client_with_grpc_https_and_api_key(monkeypatch):
    monkeypatch.setenv("QD_KEY", "secret")
    config = QdrantConfig(
        host="qdrant.internal", port=6333, prefer_grpc=True, grpc_port=6334, https=True, api_key_env="QD_KEY"
    )
    with patch("recall.adapters.qdrant_vector_store.QdrantClient") as client_cls:
        QdrantVectorStore(config)

    client_cls.assert_called_once_with(
        url="https://qdrant.internal:6333", prefer_grpc=True, grpc_port=6334, api_key="secret"
    )


def test_embedded_mode_creates_directory(tmp_path):
    path = tmp_path / "nested" / "qdrant"
    store = QdrantVectorStore(QdrantConfig(path=str(path)))
    store.close()
    assert path.is_dir()


def test_close_closes_client():
    client = MagicMock()
    QdrantVectorStore(QdrantConfig(), client=client).close()
    client.close.assert_called_once()
