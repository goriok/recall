from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from recall.config import find_config, load_config, ConfigError
from recall.qdrant_guard import ensure_qdrant
from recall.searcher import semantic_search

mcp = FastMCP("recall")


def search_knowledge(query: str, project: Optional[str] = None, top_k: int = 5) -> str:
    """Core search logic — separated for testability."""
    config_path = find_config()
    config = load_config(config_path)
    ensure_qdrant(config.qdrant.url)

    results = semantic_search(query, config=config, collection=project, top_k=top_k)

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
