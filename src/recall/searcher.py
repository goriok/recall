from __future__ import annotations

from dataclasses import dataclass, field

from recall.config import CODE_COLLECTION_PREFIX, Config, ProjectConfig
from recall.core.interfaces import VectorStore
from recall.embeddings import as_resolver
from recall.meta import check_model


class SearchError(Exception):
    pass


@dataclass
class SearchResult:
    text: str
    source: str
    collection: str
    heading: str
    score: float
    file_path: str = ""
    repo_name: str = ""
    start_line: int = 0
    end_line: int = 0
    breadcrumb: list[str] = field(default_factory=list)
    symbol_name: str = ""
    kind: str = ""
    community_name: str = ""
    is_god_node: bool = False
    related_symbols: list[str] = field(default_factory=list)


def _targets(
    config: Config, collection: str | None, kind: str | None
) -> list[tuple[str, ProjectConfig | None]]:
    if collection:
        return [(collection, config.project_for_collection(collection))]
    return [(p.collection, p) for p in config.all_projects() if kind is None or p.kind == kind]


def semantic_search(
    query: str,
    *,
    config: Config,
    vector_store: VectorStore,
    embedding_provider,
    collection: str | None = None,
    top_k: int = 5,
    min_score: float | None = None,
    kind: str | None = None,
) -> list[SearchResult]:
    resolver = as_resolver(embedding_provider)
    targets = _targets(config, collection, kind)
    if not targets:
        return []

    providers = {resolver.for_project(project).model_id: resolver.for_project(project) for _, project in targets}
    if len(providers) > 1:
        raise SearchError(
            "the selected collections use different embedding models "
            f"({', '.join(sorted(providers))}) — narrow the search to one project"
        )
    provider = next(iter(providers.values()))
    vector = provider.embed(query)

    results: list[SearchResult] = []
    for col, _ in targets:
        check_model(vector_store, col, provider.model_id, provider.dimensions)
        hits = vector_store.query(col, vector, top_k, min_score=min_score)
        for hit in hits:
            p = hit.payload
            results.append(
                SearchResult(
                    text=p.get("text", ""),
                    source=p.get("source", ""),
                    collection=col,
                    heading=p.get("heading", ""),
                    score=hit.score,
                    file_path=p.get("file_path", ""),
                    repo_name=p.get("repo_name", ""),
                    start_line=p.get("start_line", 0),
                    end_line=p.get("end_line", 0),
                    breadcrumb=list(p.get("breadcrumb") or []),
                    symbol_name=p.get("symbol_name", ""),
                    kind=p.get("kind", ""),
                    community_name=p.get("community_name", ""),
                    is_god_node=bool(p.get("is_god_node", False)),
                    related_symbols=list(p.get("related_symbols") or []),
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]


def search_code(
    query: str,
    *,
    config: Config,
    vector_store: VectorStore,
    embedding_provider,
    repo: str | None = None,
    top_k: int = 5,
    min_score: float | None = None,
) -> list[SearchResult]:
    collection = f"{CODE_COLLECTION_PREFIX}{repo}" if repo else None
    return semantic_search(
        query,
        config=config,
        vector_store=vector_store,
        embedding_provider=embedding_provider,
        collection=collection,
        top_k=top_k,
        min_score=min_score,
        kind="code",
    )
