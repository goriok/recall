from __future__ import annotations

import httpx
import pytest

from recall.adapters.openai_embedding_provider import EmbeddingProviderError, OpenAIEmbeddingProvider

SECRET = "secret-key-123"


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("EMBEDDING_KEY", SECRET)


def _provider(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    sleeps: list[float] = []
    provider = OpenAIEmbeddingProvider(
        "https://embeddings.example/v1/", "nomic-embed-text-v1-5", "EMBEDDING_KEY",
        client=client, sleep=sleeps.append, **kwargs,
    )
    provider.sleeps = sleeps
    return provider


def _ok(request: httpx.Request) -> httpx.Response:
    texts = request.read().decode()
    import json

    body = json.loads(texts)
    data = [{"index": i, "embedding": [float(len(t)), 0.0, 1.0]} for i, t in enumerate(body["input"])]
    return httpx.Response(200, json={"data": list(reversed(data))})


def test_embed_batch_posts_to_embeddings_with_bearer_key_and_sorts_by_index():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return _ok(request)

    provider = _provider(handler)
    vectors = provider.embed_batch(["a", "bbb"])

    assert seen["url"] == "https://embeddings.example/v1/embeddings"
    assert seen["auth"] == f"Bearer {SECRET}"
    assert vectors == [[1.0, 0.0, 1.0], [3.0, 0.0, 1.0]]


def test_embed_batch_splits_into_batches_of_batch_size():
    sizes = []

    def handler(request):
        import json

        sizes.append(len(json.loads(request.read())["input"]))
        return _ok(request)

    provider = _provider(handler, batch_size=2)
    provider.embed_batch(["a"] * 5)

    assert sizes == [2, 2, 1]


def test_dimensions_probe_and_model_id():
    provider = _provider(_ok)
    assert provider.model_id == "openai:nomic-embed-text-v1-5"
    assert provider.dimensions == 3
    assert provider.max_input_chars > 8000


def test_dimensions_known_after_embed_without_extra_call():
    calls = []

    def handler(request):
        calls.append(1)
        return _ok(request)

    provider = _provider(handler)
    provider.embed("hello")
    assert provider.dimensions == 3
    assert len(calls) == 1


def test_missing_api_key_env_fails_before_any_call(monkeypatch):
    monkeypatch.delenv("EMBEDDING_KEY")
    with pytest.raises(EmbeddingProviderError, match="EMBEDDING_KEY is not set"):
        OpenAIEmbeddingProvider("https://embeddings.example/v1", "m", "EMBEDDING_KEY")


@pytest.mark.parametrize("size", [0, 33, 64])
def test_batch_size_above_endpoint_limit_is_rejected(size):
    with pytest.raises(EmbeddingProviderError, match="between 1 and 32"):
        OpenAIEmbeddingProvider("https://embeddings.example/v1", "m", "EMBEDDING_KEY", batch_size=size)


@pytest.mark.parametrize("status", [429, 500, 503, 504])
def test_retryable_status_is_retried_with_backoff_then_succeeds(status):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(status, json={"error": {"code": "busy"}})
        return _ok(request)

    provider = _provider(handler)
    assert provider.embed("x") == [1.0, 0.0, 1.0]
    assert provider.sleeps == [1.0, 2.0]


def test_retry_after_header_is_honored():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"retry-after": "7"}, json={})
        return _ok(request)

    provider = _provider(handler)
    provider.embed("x")
    assert provider.sleeps == [7.0]


def test_retries_are_bounded():
    provider = _provider(lambda r: httpx.Response(503, json={}), max_retries=2)
    with pytest.raises(EmbeddingProviderError, match="HTTP 503"):
        provider.embed("x")
    assert len(provider.sleeps) == 2


@pytest.mark.parametrize("status", [400, 401, 404])
def test_non_retryable_4xx_fail_immediately_without_leaking_key(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"code": "model_not_found", "traceId": "abc123"}})

    provider = _provider(handler)
    with pytest.raises(EmbeddingProviderError) as info:
        provider.embed("x")

    assert len(calls) == 1
    assert str(status) in str(info.value)
    assert "abc123" in str(info.value)
    assert SECRET not in str(info.value)
    assert SECRET not in repr(info.value)
    assert info.value.__cause__ is None


def test_non_json_error_body_is_handled():
    provider = _provider(lambda r: httpx.Response(400, text="bad"))
    with pytest.raises(EmbeddingProviderError, match="HTTP 400"):
        provider.embed("x")


def test_transport_errors_are_retried_then_sanitized():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    provider = _provider(handler, max_retries=1)
    with pytest.raises(EmbeddingProviderError) as info:
        provider.embed("x")

    assert "ConnectError" in str(info.value)
    assert SECRET not in str(info.value)
    assert info.value.__cause__ is None
    assert len(provider.sleeps) == 1


def test_long_input_is_truncated_to_endpoint_limit():
    lengths = []

    def handler(request):
        import json

        lengths.extend(len(t) for t in json.loads(request.read())["input"])
        return _ok(request)

    provider = _provider(handler)
    provider.embed("x" * 100_000)
    assert lengths == [provider.max_input_chars]
