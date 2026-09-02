from __future__ import annotations

import ollama

# nomic-embed-text actual context: 2048 tokens (nomic-bert). ~4 chars/token → 1500 chars is safe.
_MAX_CHARS = 1500


class OllamaEmbeddingProvider:
    """EmbeddingProvider adapter backed by a local Ollama model."""

    def __init__(self, model: str, host: str) -> None:
        self._model = model
        self._client = ollama.Client(host=host)

    def embed(self, text: str) -> list[float]:
        response = self._client.embed(model=self._model, input=text[:_MAX_CHARS])
        return response.embeddings[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Send one at a time to avoid batch-level context overflow
        return [self.embed(t) for t in texts]
