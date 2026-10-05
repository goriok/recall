from __future__ import annotations

import warnings
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from recall.config import QdrantConfig
from recall.core.interfaces import CollectionInfo, Point, VectorHit

_FACET_LIMIT = 100_000
_SCROLL_PAGE = 256
_DELETE_BATCH = 500
INDEXED_FIELD = "file_path"


class QdrantVectorStore:
    """VectorStore adapter backed by Qdrant — embedded (path) by default, server (url) if configured."""

    def __init__(self, config: QdrantConfig, client: QdrantClient | None = None) -> None:
        if client is not None:
            self._client = client
        elif config.host is not None:
            self._client = QdrantClient(
                url=config.url,
                prefer_grpc=config.prefer_grpc,
                grpc_port=config.grpc_port,
                api_key=config.api_key(),
            )
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
        if self.collection_exists(name):
            self._client.delete_collection(name)
        self._client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self._client.create_payload_index(
                    collection_name=name,
                    field_name=INDEXED_FIELD,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass

    def upsert(self, name: str, points: list[Point]) -> None:
        batch_size = 100
        qdrant_points = [
            PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
        ]
        for i in range(0, len(qdrant_points), batch_size):
            self._client.upsert(collection_name=name, points=qdrant_points[i : i + batch_size])

    def query(
        self, name: str, vector: list[float], limit: int, min_score: float | None = None
    ) -> list[VectorHit]:
        try:
            response = self._client.query_points(
                collection_name=name,
                query=vector,
                limit=limit,
                score_threshold=min_score,
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

    def delete_where(self, name: str, field: str, values: list[str]) -> None:
        for i in range(0, len(values), _DELETE_BATCH):
            batch = values[i : i + _DELETE_BATCH]
            self._client.delete(
                collection_name=name,
                points_selector=FilterSelector(
                    filter=Filter(must=[FieldCondition(key=field, match=MatchAny(any=batch))])
                ),
            )

    def distinct_values(self, name: str, field: str) -> set[str]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                response = self._client.facet(collection_name=name, key=field, limit=_FACET_LIMIT)
            if len(response.hits) < _FACET_LIMIT:
                return {str(h.value) for h in response.hits}
        except Exception:
            pass
        return self._scroll_distinct(name, field)

    def _scroll_distinct(self, name: str, field: str) -> set[str]:
        values: set[str] = set()
        offset = None
        while True:
            points, offset = self._client.scroll(
                collection_name=name,
                limit=_SCROLL_PAGE,
                offset=offset,
                with_payload=[field],
                with_vectors=False,
            )
            for p in points:
                value = (p.payload or {}).get(field)
                if value is not None:
                    values.add(str(value))
            if offset is None:
                return values

    def scroll_where(self, name: str, field: str, value: str, limit: int = 10) -> list[dict]:
        try:
            points, _ = self._client.scroll(
                collection_name=name,
                scroll_filter=Filter(must=[FieldCondition(key=field, match=MatchValue(value=value))]),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            return []
        return [p.payload or {} for p in points]

    def count(self, name: str) -> int:
        return self._client.count(collection_name=name, exact=True).count

    def close(self) -> None:
        self._client.close()
