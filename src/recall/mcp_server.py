from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from recall.adapters.ollama_embedding_provider import OllamaEmbeddingProvider
from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.config import Config, find_config, load_config, ConfigError
from recall.core.interfaces import EmbeddingProvider, VectorStore
from recall.qdrant_guard import ensure_qdrant
from recall.searcher import semantic_search

mcp = FastMCP("recall")

# Built once per process and reused across calls — the embedded Qdrant store
# holds an exclusive file lock for as long as the client is open, so opening a
# fresh one per request (previous behavior) raced with the lock in server mode
# and reopened the SQLite file needlessly in embedded mode.
_vector_store: VectorStore | None = None
_embedding_provider: EmbeddingProvider | None = None


def _get_adapters(config: Config) -> tuple[VectorStore, EmbeddingProvider]:
    global _vector_store, _embedding_provider
    if _vector_store is None:
        if config.qdrant.host is not None:
            ensure_qdrant(config.qdrant.url)
        _vector_store = QdrantVectorStore(config.qdrant)
        _embedding_provider = OllamaEmbeddingProvider(config.embedding.model, config.embedding.ollama_host)
    return _vector_store, _embedding_provider


def search_knowledge(query: str, project: Optional[str] = None, top_k: int = 5) -> str:
    """Core search logic — separated for testability."""
    config_path = find_config()
    config = load_config(config_path)
    vector_store, embedding_provider = _get_adapters(config)

    results = semantic_search(
        query,
        config=config,
        vector_store=vector_store,
        embedding_provider=embedding_provider,
        collection=project,
        top_k=top_k,
    )

    if not results:
        return "No results found."

    lines = []
    for r in results:
        lines.append(f"### [{r.collection}] {r.source} (score: {r.score:.2f})")
        lines.append(r.text)
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def search_docs(
    query: str,
    project: Optional[str] = None,
    top_k: int = 5,
) -> str:
    """Search indexed project documentation semantically.

    Args:
        query: Natural language search query
        project: Optional project name to restrict search (e.g. 'mcx-companion')
        top_k: Number of results to return (default 5)
    """
    return search_knowledge(query, project=project, top_k=top_k)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
