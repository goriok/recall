from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from recall.config import QdrantConfig
from recall.core.interfaces import CollectionInfo, Point, VectorHit


class QdrantVectorStore:
    """VectorStore adapter backed by Qdrant — embedded (path) by default, server (url) if configured."""

    def __init__(self, config: QdrantConfig) -> None:
        if config.host is not None:
            self._client = QdrantClient(url=config.url)
        else:
            Path(config.path).expanduser().mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(Path(config.path).expanduser()))

    def collection_exists(self, name: str) -> bool:
        try:
            self._client.get_collection(name)
            return True
        except Exception:
            return False

    def recreate_collection(self, name: str, vector_size: int) -> None:
        self._client.recreate_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert(self, name: str, points: list[Point]) -> None:
        batch_size = 100
        qdrant_points = [
            PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
        ]
        for i in range(0, len(qdrant_points), batch_size):
            self._client.upsert(collection_name=name, points=qdrant_points[i : i + batch_size])

    def query(self, name: str, vector: list[float], limit: int) -> list[VectorHit]:
        try:
            response = self._client.query_points(
                collection_name=name,
                query=vector,
                limit=limit,
                with_payload=True,
            )
        except Exception:
            # collection may not exist yet if not ingested
            return []
        return [VectorHit(score=hit.score, payload=hit.payload or {}) for hit in response.points]

    def list_collections(self) -> list[CollectionInfo]:
        cols = self._client.get_collections().collections
        return [
            CollectionInfo(name=c.name, points_count=self._client.get_collection(c.name).points_count or 0)
            for c in cols
        ]

    def delete_collection(self, name: str) -> None:
        self._client.delete_collection(name)

    def close(self) -> None:
        self._client.close()
