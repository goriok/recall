from __future__ import annotations

import ollama

from recall.config import EmbeddingConfig


def embed(text: str, *, config: EmbeddingConfig) -> list[float]:
    """Generate an embedding vector for text using Ollama."""
    client = ollama.Client(host=config.ollama_host)
    response = client.embeddings(model=config.model, prompt=text)
    return response["embedding"]


def embed_batch(texts: list[str], *, config: EmbeddingConfig) -> list[list[float]]:
    return [embed(t, config=config) for t in texts]
