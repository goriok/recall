from __future__ import annotations

import ollama

from recall.config import EmbeddingConfig


# nomic-embed-text actual context: 2048 tokens (nomic-bert). ~4 chars/token → 1500 chars is safe.
_MAX_CHARS = 1500


def embed(text: str, *, config: EmbeddingConfig) -> list[float]:
    client = ollama.Client(host=config.ollama_host)
    response = client.embed(model=config.model, input=text[:_MAX_CHARS])
    return response.embeddings[0]


def embed_batch(texts: list[str], *, config: EmbeddingConfig) -> list[list[float]]:
    # Send one at a time to avoid batch-level context overflow
    return [embed(t, config=config) for t in texts]
