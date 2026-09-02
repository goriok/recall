from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Point:
    id: int
    vector: list[float]
    payload: dict


@dataclass
class VectorHit:
    score: float
    payload: dict = field(default_factory=dict)


@dataclass
class CollectionInfo:
    name: str
    points_count: int


class VectorStore(Protocol):
    """Secondary/driven port for a vector database (embed + upsert + similarity query)."""

    def collection_exists(self, name: str) -> bool: ...

    def recreate_collection(self, name: str, vector_size: int) -> None: ...

    def upsert(self, name: str, points: list[Point]) -> None: ...

    def query(
        self, name: str, vector: list[float], limit: int, min_score: float | None = None
    ) -> list[VectorHit]: ...

    def list_collections(self) -> list[CollectionInfo]: ...

    def delete_collection(self, name: str) -> None: ...

    def close(self) -> None:
        """Release the underlying client. Required for the embedded (path=) mode,
        which holds an exclusive lock on the storage directory until closed."""
        ...


class EmbeddingProvider(Protocol):
    """Secondary/driven port for turning text into vectors."""

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
