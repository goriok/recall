from __future__ import annotations

from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig
from recall.core.interfaces import VectorHit
from recall.searcher import semantic_search
from tests.fakes import FakeEmbeddingProvider


class _ScoredVectorStore:
    """VectorStore stub returning fixed hits with distinct scores, for min_score tests."""

    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits

    def collection_exists(self, name):
        return False

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


import pytest

from recall.config import RepoConfig, SourceConfig
from recall.core.interfaces import Point
from recall.meta import ModelMismatchError, write_meta
from recall.searcher import SearchError, search_code
from tests.fakes import FakeVectorStore


def _store_with(**collections):
    store = FakeVectorStore()
    for name, payloads in collections.items():
        store.recreate_collection(name, 4)
        store.upsert(name, [Point(id=i, vector=[0.1], payload=p) for i, p in enumerate(payloads, start=1)])
    return store


def test_results_carry_location_and_graph_metadata():
    store = _store_with(
        **{
            "code.r": [
                {
                    "text": "def f(): ...", "file_path": "pkg/a.py", "repo_name": "r", "start_line": 3,
                    "end_line": 9, "symbol_name": "f", "kind": "function", "community_name": "core",
                    "is_god_node": True, "related_symbols": ["g"],
                }
            ]
        }
    )
    config = Config(repos=[RepoConfig(name="r", root="/tmp/r")])

    results = search_code("q", config=config, vector_store=store, embedding_provider=FakeEmbeddingProvider())

    r = results[0]
    assert (r.file_path, r.start_line, r.end_line, r.symbol_name) == ("pkg/a.py", 3, 9, "f")
    assert r.repo_name == "r" and r.is_god_node and r.related_symbols == ["g"] and r.community_name == "core"


def test_search_without_collection_enumerates_all_projects_including_sources(tmp_path):
    topics = tmp_path / "ctx" / "topics"
    (topics / "auth").mkdir(parents=True)
    (topics / "auth" / "a.md").write_text("# A\n\nbody\n")
    config = Config(sources=[SourceConfig(root=str(topics))])
    store = _store_with(**{"ctx.auth": [{"text": "hit", "source": "a.md", "heading": "A"}]})

    results = semantic_search("q", config=config, vector_store=store, embedding_provider=FakeEmbeddingProvider())

    assert [r.text for r in results] == ["hit"]
    assert results[0].collection == "ctx.auth"


def test_kind_filter_separates_docs_from_code():
    config = Config(
        projects=[ProjectConfig(name="docs", path="/d", collection="docs")],
        repos=[RepoConfig(name="r", root="/r")],
    )
    store = _store_with(docs=[{"text": "doc"}], **{"code.r": [{"text": "code"}]})
    provider = FakeEmbeddingProvider()

    docs = semantic_search("q", config=config, vector_store=store, embedding_provider=provider, kind="docs")
    code = semantic_search("q", config=config, vector_store=store, embedding_provider=provider, kind="code")
    both = semantic_search("q", config=config, vector_store=store, embedding_provider=provider, top_k=10)

    assert [r.text for r in docs] == ["doc"]
    assert [r.text for r in code] == ["code"]
    assert {r.text for r in both} == {"doc", "code"}


def test_search_code_with_repo_restricts_to_that_collection():
    config = Config(repos=[RepoConfig(name="a", root="/a"), RepoConfig(name="b", root="/b")])
    store = _store_with(**{"code.a": [{"text": "from a"}], "code.b": [{"text": "from b"}]})

    results = search_code("q", config=config, vector_store=store, embedding_provider=FakeEmbeddingProvider(), repo="b")

    assert [r.text for r in results] == ["from b"]


def test_search_returns_empty_when_nothing_configured():
    assert semantic_search("q", config=Config(), vector_store=FakeVectorStore(), embedding_provider=FakeEmbeddingProvider()) == []


def test_search_refuses_collection_indexed_with_another_model():
    config = _make_config()
    store = _store_with(docs=[{"text": "x"}])
    write_meta(store, "docs", "openai:nomic-embed-text-v1-5", 768)

    with pytest.raises(ModelMismatchError, match="--recreate"):
        semantic_search("q", config=config, vector_store=store, embedding_provider=FakeEmbeddingProvider(), collection="docs")


def test_search_refuses_unfiltered_search_across_different_models():
    remote = EmbeddingConfig(provider="openai", model="m", base_url="u", api_key_env="K")
    config = Config(
        projects=[
            ProjectConfig(name="a", path="/a", collection="a"),
            ProjectConfig(name="b", path="/b", collection="b", embedding=remote),
        ]
    )

    def factory(cfg):
        return FakeEmbeddingProvider(model_id=f"{cfg.provider}:{cfg.model}")

    from recall.embeddings import ProviderResolver

    resolver = ProviderResolver(config, factory=factory)

    with pytest.raises(SearchError, match="different embedding models"):
        semantic_search("q", config=config, vector_store=FakeVectorStore(), embedding_provider=resolver)

    store = _store_with(b=[{"text": "ok"}])
    write_meta(store, "b", "openai:m", 768)
    narrowed = semantic_search("q", config=config, vector_store=store, embedding_provider=resolver, collection="b")
    assert [r.text for r in narrowed] == ["ok"]
