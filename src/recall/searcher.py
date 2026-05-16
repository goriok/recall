from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient

from recall.config import Config
from recall.embedder import embed


@dataclass
class SearchResult:
    text: str
    source: str
    collection: str
    heading: str
    score: float


def semantic_search(
    query: str,
    *,
    config: Config,
    collection: str | None = None,
    top_k: int = 5,
) -> list[SearchResult]:
    vector = embed(query, config=config.embedding)
    client = QdrantClient(url=config.qdrant.url)

    collections = (
        [collection] if collection else [p.collection for p in config.projects]
    )

    results: list[SearchResult] = []
    for col in collections:
        try:
            response = client.query_points(
                collection_name=col,
                query=vector,
                limit=top_k,
                with_payload=True,
            )
            for hit in response.points:
                payload = hit.payload or {}
                results.append(
                    SearchResult(
                        text=payload.get("text", ""),
                        source=payload.get("source", ""),
                        collection=col,
                        heading=payload.get("heading", ""),
                        score=hit.score,
                    )
                )
        except Exception:
            # collection may not exist yet if not ingested
            continue

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]
