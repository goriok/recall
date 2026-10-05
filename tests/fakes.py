from __future__ import annotations

from recall.core.interfaces import CollectionInfo, Point, VectorHit


class FakeVectorStore:
    """In-memory VectorStore for tests — no network, no mock.patch."""

    def __init__(self) -> None:
        self.collections: dict[str, list[Point]] = {}

    def collection_exists(self, name: str) -> bool:
        return name in self.collections

    def recreate_collection(self, name: str, vector_size: int) -> None:
        self.collections[name] = []

    def upsert(self, name: str, points: list[Point]) -> None:
        existing = self.collections.setdefault(name, [])
        by_id = {p.id: i for i, p in enumerate(existing)}
        for point in points:
            if point.id in by_id:
                existing[by_id[point.id]] = point
            else:
                by_id[point.id] = len(existing)
                existing.append(point)

    def query(
        self, name: str, vector: list[float], limit: int, min_score: float | None = None
    ) -> list[VectorHit]:
        points = self.collections.get(name, [])
        hits = [VectorHit(score=1.0, payload=p.payload) for p in points]
        if min_score is not None:
            hits = [h for h in hits if h.score >= min_score]
        return hits[:limit]

    def list_collections(self) -> list[CollectionInfo]:
        return [
            CollectionInfo(name=name, points_count=len(points))
            for name, points in self.collections.items()
        ]

    def delete_collection(self, name: str) -> None:
        self.collections.pop(name, None)

    def delete_where(self, name: str, field: str, values: list[str]) -> None:
        wanted = set(values)
        self.collections[name] = [
            p for p in self.collections.get(name, []) if p.payload.get(field) not in wanted
        ]

    def distinct_values(self, name: str, field: str) -> set[str]:
        return {
            str(p.payload[field]) for p in self.collections.get(name, []) if field in p.payload
        }

    def scroll_where(self, name: str, field: str, value: str, limit: int = 10) -> list[dict]:
        matches = [p.payload for p in self.collections.get(name, []) if p.payload.get(field) == value]
        return matches[:limit]

    def count(self, name: str) -> int:
        return len(self.collections.get(name, []))

    def close(self) -> None:
        pass


class FakeEmbeddingProvider:
    """Deterministic EmbeddingProvider for tests — no Ollama call."""

    def __init__(
        self, dim: int = 768, model_id: str = "ollama:nomic-embed-text", max_input_chars: int = 1_000_000
    ) -> None:
        self.dim = dim
        self._model_id = model_id
        self._max_input_chars = max_input_chars
        self.calls: list[list[str]] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimensions(self) -> int:
        return self.dim

    @property
    def max_input_chars(self) -> int:
        return self._max_input_chars

    def embed(self, text: str) -> list[float]:
        return [0.1] * self.dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self.embed(t) for t in texts]
