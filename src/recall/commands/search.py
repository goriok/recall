from __future__ import annotations

from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from recall.adapters.openai_embedding_provider import EmbeddingProviderError
from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.config import find_config, load_config, ConfigError
from recall.embeddings import ProviderResolver
from recall.meta import ModelMismatchError
from recall.searcher import SearchError, semantic_search
from recall.qdrant_guard import ensure_qdrant

console = Console()


def search(
    query: str = typer.Argument(..., help="Search query"),
    collection: Optional[str] = typer.Option(None, "--in", metavar="PROJECT", help="Restrict to a specific project collection"),
    top_k: int = typer.Option(5, "--top", help="Number of results to return"),
    min_score: Optional[float] = typer.Option(None, "--min-score", help="Discard results below this similarity score (0-1)"),
):
    """Search across indexed docs."""
    try:
        config_path = find_config()
        config = load_config(config_path)
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if config.qdrant.host is not None:
        ensure_qdrant(config.qdrant.url, config.qdrant.api_key())
    vector_store = QdrantVectorStore(config.qdrant)
    resolver = ProviderResolver(config)

    try:
        results = semantic_search(
            query,
            config=config,
            vector_store=vector_store,
            embedding_provider=resolver,
            collection=collection,
            top_k=top_k,
            min_score=min_score,
            kind=None if collection else "docs",
        )
    except (SearchError, ModelMismatchError, EmbeddingProviderError, ConfigError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        vector_store.close()

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    for r in results:
        header = Text()
        header.append(f"{r.collection}", style="bold cyan")
        where = f"{r.file_path}:{r.start_line}-{r.end_line}" if r.file_path else r.source
        header.append(f" · {where}", style="dim")
        header.append(f" · score: {r.score:.2f}", style="dim green")
        console.print(Panel(r.text[:500], title=header, border_style="dim"))
