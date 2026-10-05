from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Point:
    id: int | str
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

    def delete_where(self, name: str, field: str, values: list[str]) -> None: ...

    def distinct_values(self, name: str, field: str) -> set[str]: ...

    def scroll_where(self, name: str, field: str, value: str, limit: int = 10) -> list[dict]: ...

    def count(self, name: str) -> int: ...

    def close(self) -> None:
        """Release the underlying client. Required for the embedded (path=) mode,
        which holds an exclusive lock on the storage directory until closed."""
        ...


class EmbeddingProvider(Protocol):
    """Secondary/driven port for turning text into vectors."""

    @property
    def model_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    @property
    def max_input_chars(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
