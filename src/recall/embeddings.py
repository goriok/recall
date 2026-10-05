from __future__ import annotations

from typing import Callable

from recall.adapters.ollama_embedding_provider import OllamaEmbeddingProvider
from recall.adapters.openai_embedding_provider import OpenAIEmbeddingProvider
from recall.config import Config, ConfigError, EmbeddingConfig, ProjectConfig
from recall.core.interfaces import EmbeddingProvider


def build_embedding_provider(cfg: EmbeddingConfig) -> EmbeddingProvider:
    if cfg.provider == "ollama":
        return OllamaEmbeddingProvider(cfg.model, cfg.ollama_host, max_chars=cfg.max_chars)
    if cfg.provider == "openai":
        if not cfg.base_url or not cfg.api_key_env:
            raise ConfigError("embedding.provider = 'openai' requires base_url and api_key_env")
        return OpenAIEmbeddingProvider(cfg.base_url, cfg.model, cfg.api_key_env, cfg.batch_size)
    raise ConfigError(f"unknown embedding provider '{cfg.provider}'")


def _key(cfg: EmbeddingConfig) -> tuple:
    return (cfg.provider, cfg.model, cfg.ollama_host, cfg.base_url, cfg.api_key_env, cfg.batch_size, cfg.max_chars)


class ProviderResolver:
    """Builds one embedding provider per distinct embedding config and reuses it."""

    def __init__(
        self,
        config: Config,
        factory: Callable[[EmbeddingConfig], EmbeddingProvider] = build_embedding_provider,
    ) -> None:
        self._config = config
        self._factory = factory
        self._cache: dict[tuple, EmbeddingProvider] = {}

    def for_project(self, project: ProjectConfig | None) -> EmbeddingProvider:
        cfg = self._config.embedding_for(project)
        key = _key(cfg)
        if key not in self._cache:
            self._cache[key] = self._factory(cfg)
        return self._cache[key]


class FixedResolver:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def for_project(self, project: ProjectConfig | None) -> EmbeddingProvider:
        return self._provider


def as_resolver(source: object) -> ProviderResolver | FixedResolver:
    if hasattr(source, "for_project"):
        return source  # type: ignore[return-value]
    return FixedResolver(source)  # type: ignore[arg-type]
