from __future__ import annotations

import logging
import os
import time
from typing import Callable

import httpx

from recall.config import MAX_EMBEDDING_BATCH

logging.getLogger("httpx").setLevel(logging.WARNING)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_INPUT_CHARS = 24000


class EmbeddingProviderError(Exception):
    pass


class OpenAIEmbeddingProvider:
    """EmbeddingProvider for an OpenAI-compatible /embeddings endpoint.

    The endpoint only computes vectors; nothing is stored there. Errors are re-raised
    sanitized so the API key held in request headers never reaches a log or traceback.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str,
        batch_size: int = MAX_EMBEDDING_BATCH,
        max_retries: int = 4,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 1 <= batch_size <= MAX_EMBEDDING_BATCH:
            raise EmbeddingProviderError(f"batch_size must be between 1 and {MAX_EMBEDDING_BATCH}")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise EmbeddingProviderError(f"environment variable {api_key_env} is not set")
        self._url = base_url.rstrip("/") + "/embeddings"
        self._model = model
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep
        self._dimensions: int | None = None

    @property
    def model_id(self) -> str:
        return f"openai:{self._model}"

    @property
    def max_input_chars(self) -> int:
        return _MAX_INPUT_CHARS

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            self._dimensions = len(self.embed("dimension probe"))
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = [t[:_MAX_INPUT_CHARS] for t in texts[i : i + self._batch_size]]
            vectors.extend(self._post(batch))
        if vectors and self._dimensions is None:
            self._dimensions = len(vectors[0])
        return vectors

    def _post(self, batch: list[str]) -> list[list[float]]:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    self._url, headers=self._headers, json={"model": self._model, "input": batch}
                )
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise EmbeddingProviderError(
                        f"embedding request failed: {type(exc).__name__}"
                    ) from None
                self._sleep(self._backoff(attempt, None))
                continue
            if response.status_code == 200:
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                return [item["embedding"] for item in data]
            if response.status_code in _RETRY_STATUSES and attempt < self._max_retries:
                self._sleep(self._backoff(attempt, response))
                continue
            raise EmbeddingProviderError(self._describe(response)) from None
        raise EmbeddingProviderError("embedding request failed")

    @staticmethod
    def _backoff(attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(float(retry_after), 60.0)
                except ValueError:
                    pass
        return min(2.0**attempt, 30.0)

    @staticmethod
    def _describe(response: httpx.Response) -> str:
        code = trace = ""
        try:
            error = response.json().get("error", {})
            code = str(error.get("code") or error.get("type") or "")
            trace = str(error.get("traceId") or "")
        except ValueError:
            pass
        return f"embedding endpoint returned HTTP {response.status_code} {code} traceId={trace}".strip()
