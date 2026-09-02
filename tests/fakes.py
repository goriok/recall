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
        self.collections.setdefault(name, [])
        self.collections[name].extend(points)

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

    def close(self) -> None:
        pass


class FakeEmbeddingProvider:
    """Deterministic EmbeddingProvider for tests — no Ollama call."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        return [0.1] * self.dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
