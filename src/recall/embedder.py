from __future__ import annotations

import ollama

from recall.config import EmbeddingConfig


def embed(text: str, *, config: EmbeddingConfig) -> list[float]:
    """Generate an embedding vector for text using Ollama."""
    response = ollama.embeddings(
        model=config.model,
        prompt=text,
        options={"host": config.ollama_host} if config.ollama_host != "http://localhost:11434" else {},
    )
    return response["embedding"]


def embed_batch(texts: list[str], *, config: EmbeddingConfig) -> list[list[float]]:
    return [embed(t, config=config) for t in texts]
