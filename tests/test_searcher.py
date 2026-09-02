from __future__ import annotations

from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig
from recall.core.interfaces import VectorHit
from recall.searcher import semantic_search
from tests.fakes import FakeEmbeddingProvider


class _ScoredVectorStore:
    """VectorStore stub returning fixed hits with distinct scores, for min_score tests."""

    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits

    def query(self, name, vector, limit, min_score=None):
        hits = self._hits
        if min_score is not None:
            hits = [h for h in hits if h.score >= min_score]
        return hits[:limit]


def _make_config() -> Config:
    return Config(
        qdrant=QdrantConfig(),
        embedding=EmbeddingConfig(),
        projects=[ProjectConfig(name="docs", path="/tmp/docs", collection="docs")],
    )


def test_semantic_search_without_min_score_returns_all_hits():
    store = _ScoredVectorStore(
        [
            VectorHit(score=0.9, payload={"text": "a", "source": "a.md", "heading": "A"}),
            VectorHit(score=0.3, payload={"text": "b", "source": "b.md", "heading": "B"}),
        ]
    )

    results = semantic_search(
        "query",
        config=_make_config(),
        vector_store=store,
        embedding_provider=FakeEmbeddingProvider(),
        collection="docs",
    )

    assert [r.score for r in results] == [0.9, 0.3]


def test_semantic_search_with_min_score_filters_low_scores():
    store = _ScoredVectorStore(
        [
            VectorHit(score=0.9, payload={"text": "a", "source": "a.md", "heading": "A"}),
            VectorHit(score=0.3, payload={"text": "b", "source": "b.md", "heading": "B"}),
        ]
    )

    results = semantic_search(
        "query",
        config=_make_config(),
        vector_store=store,
        embedding_provider=FakeEmbeddingProvider(),
        collection="docs",
        min_score=0.5,
    )

    assert [r.score for r in results] == [0.9]
