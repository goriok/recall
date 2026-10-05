from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from recall.adapters.ollama_embedding_provider import OllamaEmbeddingProvider
from recall.adapters.openai_embedding_provider import OpenAIEmbeddingProvider
from recall.config import Config, ConfigError, EmbeddingConfig, ProjectConfig
from recall.embeddings import FixedResolver, ProviderResolver, as_resolver, build_embedding_provider
from tests.fakes import FakeEmbeddingProvider


def _ollama_client(dim=3):
    client = MagicMock()
    client.embed.side_effect = lambda model, input: MagicMock(embeddings=[[0.5] * dim])
    return client


def test_ollama_provider_truncates_input_and_reports_model():
    client = _ollama_client()
    provider = OllamaEmbeddingProvider("nomic-embed-text", "http://x", max_chars=10, client=client)

    provider.embed("a" * 50)

    assert client.embed.call_args.kwargs["input"] == "a" * 10
    assert provider.model_id == "ollama:nomic-embed-text"
    assert provider.max_input_chars == 10


def test_ollama_provider_default_max_chars_is_1500():
    provider = OllamaEmbeddingProvider("m", "http://x", client=_ollama_client())
    assert provider.max_input_chars == 1500


def test_ollama_provider_dimensions_probe_is_cached():
    client = _ollama_client(dim=5)
    provider = OllamaEmbeddingProvider("m", "http://x", client=client)

    assert provider.dimensions == 5
    assert provider.dimensions == 5
    assert client.embed.call_count == 1


def test_ollama_embed_batch_sends_one_by_one():
    client = _ollama_client()
    provider = OllamaEmbeddingProvider("m", "http://x", client=client)

    vectors = provider.embed_batch(["a", "b", "c"])

    assert len(vectors) == 3
    assert client.embed.call_count == 3


def test_build_provider_ollama_default():
    provider = build_embedding_provider(EmbeddingConfig())
    assert isinstance(provider, OllamaEmbeddingProvider)


def test_build_provider_openai(monkeypatch):
    monkeypatch.setenv("EMBEDDING_KEY", "k")
    cfg = EmbeddingConfig(provider="openai", model="m", base_url="https://embeddings.example/v1", api_key_env="EMBEDDING_KEY")
    assert isinstance(build_embedding_provider(cfg), OpenAIEmbeddingProvider)


def test_build_provider_openai_requires_url_and_key_env():
    with pytest.raises(ConfigError, match="base_url and api_key_env"):
        build_embedding_provider(EmbeddingConfig(provider="openai"))


def test_build_provider_rejects_unknown_provider():
    with pytest.raises(ConfigError, match="unknown embedding provider"):
        build_embedding_provider(EmbeddingConfig(provider="voyage"))


def test_resolver_caches_by_embedding_config_and_honors_overrides():
    built = []

    def factory(cfg):
        built.append(cfg)
        return FakeEmbeddingProvider(model_id=f"{cfg.provider}:{cfg.model}")

    remote = EmbeddingConfig(provider="openai", model="remote-model", base_url="u", api_key_env="K")
    config = Config(
        embedding=EmbeddingConfig(),
        projects=[
            ProjectConfig(name="a", path="/a", collection="a"),
            ProjectConfig(name="b", path="/b", collection="b"),
            ProjectConfig(name="c", path="/c", collection="c", embedding=remote),
        ],
    )
    resolver = ProviderResolver(config, factory=factory)

    pa, pb, pc = (resolver.for_project(p) for p in config.projects)

    assert pa is pb
    assert pc is not pa
    assert pc.model_id == "openai:remote-model"
    assert len(built) == 2
    assert resolver.for_project(None) is pa


def test_as_resolver_wraps_plain_provider_and_passes_resolvers_through():
    provider = FakeEmbeddingProvider()
    assert isinstance(as_resolver(provider), FixedResolver)
    assert as_resolver(provider).for_project(None) is provider
    resolver = ProviderResolver(Config())
    assert as_resolver(resolver) is resolver
