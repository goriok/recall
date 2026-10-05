from __future__ import annotations

import ollama

DEFAULT_MAX_CHARS = 1500


class OllamaEmbeddingProvider:
    """EmbeddingProvider adapter backed by a local Ollama model.

    nomic-embed-text actual context is 2048 tokens (nomic-bert); the default
    max_chars of 1500 keeps one chunk inside it. Longer chunks lose their tail.
    """

    def __init__(
        self, model: str, host: str, max_chars: int = DEFAULT_MAX_CHARS, client: ollama.Client | None = None
    ) -> None:
        self._model = model
        self._max_chars = max_chars
        self._client = client or ollama.Client(host=host)
        self._dimensions: int | None = None

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    @property
    def max_input_chars(self) -> int:
        return self._max_chars

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            self._dimensions = len(self.embed("dimension probe"))
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        response = self._client.embed(model=self._model, input=text[: self._max_chars])
        vector = list(response.embeddings[0])
        if self._dimensions is None:
            self._dimensions = len(vector)
        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Send one at a time to avoid batch-level context overflow
        return [self.embed(t) for t in texts]
