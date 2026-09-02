from __future__ import annotations

from dataclasses import dataclass

from recall.config import Config
from recall.core.interfaces import EmbeddingProvider, VectorStore


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
    vector_store: VectorStore,
    embedding_provider: EmbeddingProvider,
    collection: str | None = None,
    top_k: int = 5,
    min_score: float | None = None,
) -> list[SearchResult]:
    vector = embedding_provider.embed(query)

    collections = (
        [collection] if collection else [p.collection for p in config.projects]
    )

    results: list[SearchResult] = []
    for col in collections:
        hits = vector_store.query(col, vector, top_k, min_score=min_score)
        for hit in hits:
            results.append(
                SearchResult(
                    text=hit.payload.get("text", ""),
                    source=hit.payload.get("source", ""),
                    collection=col,
                    heading=hit.payload.get("heading", ""),
                    score=hit.score,
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]
