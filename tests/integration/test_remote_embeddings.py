from __future__ import annotations

import os

import pytest

from recall.adapters.openai_embedding_provider import EmbeddingProviderError, OpenAIEmbeddingProvider

pytestmark = pytest.mark.remote

BASE_URL = os.environ.get("RECALL_TEST_EMBEDDING_URL")
KEY_ENV = "RECALL_EMBEDDING_API_KEY"


@pytest.fixture
def provider():
    if not (BASE_URL and os.environ.get(KEY_ENV)):
        pytest.skip("RECALL_TEST_EMBEDDING_URL and RECALL_EMBEDDING_API_KEY are not set")
    return OpenAIEmbeddingProvider(BASE_URL, os.environ.get("RECALL_TEST_EMBEDDING_MODEL", "nomic-embed-text-v1-5"), KEY_ENV)


def test_embeddings_have_768_dimensions(provider):
    vectors = provider.embed_batch(["def authenticate(token): ...", "how does login work"])
    assert [len(v) for v in vectors] == [768, 768]
    assert provider.dimensions == 768


def test_more_than_one_endpoint_batch_is_split_transparently(provider):
    vectors = provider.embed_batch([f"synthetic text {i}" for i in range(70)])
    assert len(vectors) == 70


def test_long_inputs_are_not_cut_at_1500_characters(provider):
    base = "authentication flow " * 100
    short = provider.embed(base[:1500])
    long = provider.embed(base + " completely different tail about kubernetes deployment " * 40)
    assert short != long


def test_unknown_model_fails_fast_with_a_sanitized_error(monkeypatch):
    if not (BASE_URL and os.environ.get(KEY_ENV)):
        pytest.skip("RECALL_TEST_EMBEDDING_URL and RECALL_EMBEDDING_API_KEY are not set")
    provider = OpenAIEmbeddingProvider(BASE_URL, "no-such-model", KEY_ENV)
    with pytest.raises(EmbeddingProviderError) as info:
        provider.embed("x")
    assert os.environ[KEY_ENV] not in str(info.value)
