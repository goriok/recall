from __future__ import annotations

import atexit
from typing import Optional

from mcp.server.fastmcp import FastMCP

from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.adapters.openai_embedding_provider import EmbeddingProviderError
from recall.config import CODE_COLLECTION_PREFIX, Config, ConfigError, find_config, load_config
from recall.core.interfaces import VectorStore
from recall.embeddings import ProviderResolver
from recall.meta import LEGACY_MODEL_ID, ModelMismatchError, read_meta
from recall.qdrant_guard import ensure_qdrant
from recall.searcher import SearchError, SearchResult, search_code, semantic_search

mcp = FastMCP("recall")

# Built once per process and reused across calls — the embedded Qdrant store
# holds an exclusive file lock for as long as the client is open, so opening a
# fresh one per request (previous behavior) raced with the lock in server mode
# and reopened the SQLite file needlessly in embedded mode.
_vector_store: VectorStore | None = None
_embedding_provider: ProviderResolver | None = None


def _get_adapters(config: Config) -> tuple[VectorStore, ProviderResolver]:
    global _vector_store, _embedding_provider
    if _vector_store is None:
        if config.qdrant.host is not None:
            ensure_qdrant(config.qdrant.url, config.qdrant.api_key())
        _vector_store = QdrantVectorStore(config.qdrant)
        atexit.register(_vector_store.close)
        _embedding_provider = ProviderResolver(config)
    return _vector_store, _embedding_provider


def _format(results: list[SearchResult]) -> str:
    lines = []
    for r in results:
        if r.file_path:
            location = f"{r.file_path}:{r.start_line}-{r.end_line}"
            lines.append(f"### [{r.collection}] {location} (score: {r.score:.2f})")
            if r.repo_name:
                lines.append(f"repo: {r.repo_name}")
            if r.symbol_name:
                lines.append(f"symbol: {r.symbol_name}")
            if r.breadcrumb:
                lines.append(f"section: {' > '.join(r.breadcrumb)}")
            if r.community_name:
                lines.append(f"community: {r.community_name}")
            if r.is_god_node:
                lines.append("god_node: true")
            if r.related_symbols:
                lines.append(f"related: {', '.join(r.related_symbols)}")
        else:
            lines.append(f"### [{r.collection}] {r.source} (score: {r.score:.2f})")
        lines.append(r.text)
        lines.append("")
    return "\n".join(lines)


def _is_code_collection(config: Config, name: str) -> bool:
    project = config.project_for_collection(name)
    return name.startswith(CODE_COLLECTION_PREFIX) or (project is not None and project.kind == "code")


def search_knowledge(
    query: str,
    project: Optional[str] = None,
    top_k: int = 5,
    min_score: Optional[float] = None,
) -> str:
    """Core search logic — separated for testability."""
    config = load_config(find_config())
    if project and _is_code_collection(config, project):
        return f"'{project}' is a code collection — use search_code(repo=...) instead."
    vector_store, embedding_provider = _get_adapters(config)

    try:
        results = semantic_search(
            query,
            config=config,
            vector_store=vector_store,
            embedding_provider=embedding_provider,
            collection=project,
            top_k=top_k,
            min_score=min_score,
            kind="docs",
        )
    except (SearchError, ModelMismatchError) as exc:
        return str(exc)

    return _format(results) if results else "No results found."


def search_code_knowledge(
    query: str,
    repo: Optional[str] = None,
    top_k: int = 5,
    min_score: Optional[float] = None,
) -> str:
    config = load_config(find_config())
    if not config.repos:
        return "No code repositories configured — add a [[repos]] entry to recall.toml."
    vector_store, embedding_provider = _get_adapters(config)
    try:
        results = search_code(
            query,
            config=config,
            vector_store=vector_store,
            embedding_provider=embedding_provider,
            repo=repo,
            top_k=top_k,
            min_score=min_score,
        )
    except (SearchError, ModelMismatchError) as exc:
        return str(exc)
    return _format(results) if results else "No results found."


def explain_architecture_text(repo: str) -> str:
    config = load_config(find_config())
    known = {r.name for r in config.repos}
    if repo not in known:
        return f"Unknown repo '{repo}'. Configured repos: {', '.join(sorted(known)) or 'none'}."
    vector_store, _ = _get_adapters(config)
    meta = read_meta(vector_store, f"{CODE_COLLECTION_PREFIX}{repo}")
    if not meta or not meta.get("report"):
        return f"No architecture report for '{repo}' — run 'recall ingest {repo}' with Graphify installed."
    god_nodes = meta.get("god_nodes") or []
    lines = [f"# Architecture of {repo}", ""]
    if god_nodes:
        lines += ["## God nodes (most connected)", *[f"- {name}" for name in god_nodes], ""]
    lines.append(meta["report"])
    return "\n".join(lines)


def list_sources_text() -> str:
    config = load_config(find_config())
    projects = config.all_projects()
    if not projects:
        return "Nothing configured — add [[projects]], [[sources]] or [[repos]] to recall.toml."
    vector_store, resolver = _get_adapters(config)
    points = {c.name: c.points_count for c in vector_store.list_collections()}
    lines = []
    for project in projects:
        collection = project.collection
        label = f"{collection} ({project.kind}, repo {project.effective_repo_name})"
        if collection not in points:
            lines.append(f"- {label}: not indexed yet — run `recall ingest {project.name}`")
            continue
        meta = read_meta(vector_store, collection)
        stored = meta["model_id"] if meta else f"{LEGACY_MODEL_ID} (legacy, no record)"
        details = [f"{points[collection]} points", f"model {stored}"]
        if meta and meta.get("files"):
            details.append(f"{meta['files']} files")
        details.append(f"indexed {meta['indexed_at']}" if meta and meta.get("indexed_at") else "indexed at unknown time")
        try:
            configured = resolver.for_project(project).model_id
        except (EmbeddingProviderError, ConfigError) as exc:
            details.append(f"embedding provider unavailable: {exc}")
        else:
            expected = meta["model_id"] if meta else LEGACY_MODEL_ID
            if configured != expected:
                details.append(f"MODEL MISMATCH (configured {configured}) — run `recall ingest {project.name} --recreate`")
        lines.append(f"- {label}: " + ", ".join(details))
    return "\n".join(lines)


@mcp.tool()
def search_docs(
    query: str,
    project: Optional[str] = None,
    top_k: int = 5,
    min_score: Optional[float] = None,
) -> str:
    """Search indexed project documentation semantically.

    Args:
        query: Natural language search query
        project: Optional project name to restrict search (e.g. 'mcx-companion')
        top_k: Number of results to return (default 5)
        min_score: Optional similarity cutoff (0-1). Raise it (e.g. 0.6-0.7) when
            results look unrelated to the query; lower or omit it to cast a wider
            net when a tighter search comes back empty.
    """
    return search_knowledge(query, project=project, top_k=top_k, min_score=min_score)


@mcp.tool(name="search_code")
def search_code_mcp(
    query: str,
    repo: Optional[str] = None,
    top_k: int = 5,
    min_score: Optional[float] = None,
) -> str:
    """Search indexed source code semantically.

    Each result gives repo, file_path (relative to that repo's root), the line range
    start-end, the symbol name, and graph context (community, god_node, related symbols).
    Resolve file_path against your checkout of the repo, then read or edit those lines.

    Args:
        query: Natural language or identifier-style query
        repo: Optional repo name to restrict the search
        top_k: Number of results to return (default 5)
        min_score: Optional similarity cutoff (0-1)
    """
    return search_code_knowledge(query, repo=repo, top_k=top_k, min_score=min_score)


@mcp.tool()
def explain_architecture(repo: str) -> str:
    """Summarize a code repo's architecture: its god nodes and the Graphify report.

    Args:
        repo: Repo name as configured in recall.toml
    """
    return explain_architecture_text(repo)


@mcp.tool()
def list_sources() -> str:
    """List what is indexed: each project or repo with its kind, collection, point count, embedding model and last ingest time.

    Call this first when you do not know which repos or topics are available, or to check
    whether an index is stale or built with a different model than the one configured.
    """
    return list_sources_text()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
