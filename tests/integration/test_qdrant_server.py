from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import pytest

from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.config import QdrantConfig
from recall.core.interfaces import Point
from recall.meta import read_meta, write_meta

pytestmark = pytest.mark.integration

URL = os.environ.get("RECALL_TEST_QDRANT_URL")


@pytest.fixture
def store():
    if not URL:
        pytest.skip("RECALL_TEST_QDRANT_URL is not set")
    parsed = urlparse(URL)
    prefer_grpc = bool(os.environ.get("RECALL_TEST_QDRANT_GRPC_PORT"))
    config = QdrantConfig(
        host=parsed.hostname,
        port=parsed.port or 6333,
        prefer_grpc=prefer_grpc,
        grpc_port=int(os.environ.get("RECALL_TEST_QDRANT_GRPC_PORT", "6334")),
    )
    vector_store = QdrantVectorStore(config)
    created: list[str] = []
    vector_store.created = created
    yield vector_store
    for name in created:
        vector_store.delete_collection(name)
    vector_store.close()


def _name(store, prefix="recall-it"):
    name = f"{prefix}-{uuid.uuid4().hex[:8]}"
    store.created.append(name)
    return name


def _points(n):
    return [
        Point(id=i, vector=[1.0, 0.0], payload={"file_path": f"src/file{i}.py", "text": f"t{i}"})
        for i in range(1, n + 1)
    ]


def test_recreate_upsert_query_count(store):
    name = _name(store)
    store.recreate_collection(name, 2)
    store.upsert(name, _points(3))

    assert store.collection_exists(name)
    assert store.count(name) == 3
    assert len(store.query(name, [1.0, 0.0], 5)) == 3


def test_delete_where_and_distinct_values_use_the_payload_index(store):
    name = _name(store)
    store.recreate_collection(name, 2)
    store.upsert(name, _points(40))

    assert len(store.distinct_values(name, "file_path")) == 40

    store.delete_where(name, "file_path", ["src/file1.py", "src/file2.py"])

    remaining = store.distinct_values(name, "file_path")
    assert len(remaining) == 38 and "src/file1.py" not in remaining


def test_scroll_where_and_string_point_ids(store):
    name = _name(store)
    store.recreate_collection(name, 2)
    point_id = str(uuid.uuid4())
    store.upsert(name, [Point(id=point_id, vector=[1.0, 0.0], payload={"file_path": "a.py", "k": "v"})])
    store.upsert(name, [Point(id=point_id, vector=[1.0, 0.0], payload={"file_path": "a.py", "k": "v2"})])

    assert store.count(name) == 1
    assert store.scroll_where(name, "file_path", "a.py")[0]["k"] == "v2"


def test_recall_meta_roundtrip_on_a_server(store):
    from recall.meta import META_COLLECTION

    name = _name(store)
    write_meta(store, name, "openai:nomic-embed-text-v1-5", 768, report="r")

    meta = read_meta(store, name)

    assert meta["model_id"] == "openai:nomic-embed-text-v1-5"
    assert meta["report"] == "r"
    store.delete_where(META_COLLECTION, "collection", [name])
