from __future__ import annotations

import uuid

from recall.core.interfaces import Point, VectorStore

META_COLLECTION = "recall-meta"
_META_NAMESPACE = uuid.UUID("5f2b8a3e-7c41-4d6a-9e0b-1a2c3d4e5f60")
LEGACY_MODEL_ID = "ollama:nomic-embed-text"
LEGACY_DIMENSIONS = 768


class ModelMismatchError(Exception):
    pass


def _meta_id(collection: str) -> str:
    return str(uuid.uuid5(_META_NAMESPACE, collection))


def write_meta(
    store: VectorStore, collection: str, model_id: str, dimensions: int, **extra: object
) -> None:
    if not store.collection_exists(META_COLLECTION):
        store.recreate_collection(META_COLLECTION, 1)
    payload = {"collection": collection, "model_id": model_id, "dimensions": dimensions, **extra}
    store.upsert(META_COLLECTION, [Point(id=_meta_id(collection), vector=[1.0], payload=payload)])


def read_meta(store: VectorStore, collection: str) -> dict | None:
    if not store.collection_exists(META_COLLECTION):
        return None
    found = store.scroll_where(META_COLLECTION, "collection", collection, 1)
    return found[0] if found else None


def delete_meta(store: VectorStore, collection: str) -> None:
    if store.collection_exists(META_COLLECTION):
        store.delete_where(META_COLLECTION, "collection", [collection])


def check_model(store: VectorStore, collection: str, model_id: str, dimensions: int) -> None:
    if not store.collection_exists(collection):
        return
    meta = read_meta(store, collection)
    stored_model = meta["model_id"] if meta else LEGACY_MODEL_ID
    stored_dims = meta["dimensions"] if meta else LEGACY_DIMENSIONS
    if stored_model != model_id or stored_dims != dimensions:
        raise ModelMismatchError(
            f"collection '{collection}' was indexed with {stored_model} ({stored_dims} dims) "
            f"but the configured embedding is {model_id} ({dimensions} dims) — "
            f"re-run 'recall ingest --recreate' for it"
        )
