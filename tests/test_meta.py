from __future__ import annotations

import pytest

from recall.meta import (
    META_COLLECTION,
    ModelMismatchError,
    check_model,
    delete_meta,
    read_meta,
    write_meta,
)
from tests.fakes import FakeVectorStore


def test_write_and_read_meta_roundtrip():
    store = FakeVectorStore()
    write_meta(store, "docs.a", "openai:nomic", 768, repo_name="r")

    meta = read_meta(store, "docs.a")

    assert meta["model_id"] == "openai:nomic"
    assert meta["dimensions"] == 768
    assert meta["repo_name"] == "r"


def test_write_meta_is_idempotent_per_collection():
    store = FakeVectorStore()
    write_meta(store, "docs.a", "m1", 4)
    write_meta(store, "docs.a", "m2", 4)

    assert store.count(META_COLLECTION) == 1
    assert read_meta(store, "docs.a")["model_id"] == "m2"


def test_read_meta_returns_none_without_registry_or_entry():
    store = FakeVectorStore()
    assert read_meta(store, "docs.a") is None
    write_meta(store, "docs.b", "m", 4)
    assert read_meta(store, "docs.a") is None


def test_delete_meta_removes_only_that_collection():
    store = FakeVectorStore()
    write_meta(store, "a", "m", 4)
    write_meta(store, "b", "m", 4)

    delete_meta(store, "a")

    assert read_meta(store, "a") is None
    assert read_meta(store, "b") is not None


def test_delete_meta_without_registry_is_noop():
    delete_meta(FakeVectorStore(), "a")


def test_check_model_accepts_matching_model():
    store = FakeVectorStore()
    store.recreate_collection("docs", 4)
    write_meta(store, "docs", "m", 4)
    check_model(store, "docs", "m", 4)


def test_check_model_rejects_different_model():
    store = FakeVectorStore()
    store.recreate_collection("docs", 4)
    write_meta(store, "docs", "old", 4)
    with pytest.raises(ModelMismatchError, match="--recreate"):
        check_model(store, "docs", "new", 4)


def test_check_model_treats_missing_meta_as_legacy_ollama():
    store = FakeVectorStore()
    store.recreate_collection("docs", 768)
    check_model(store, "docs", "ollama:nomic-embed-text", 768)
    with pytest.raises(ModelMismatchError):
        check_model(store, "docs", "openai:nomic-embed-text-v1-5", 768)


def test_check_model_ignores_missing_collection():
    check_model(FakeVectorStore(), "ghost", "anything", 1)
