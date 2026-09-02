from __future__ import annotations

from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from recall.adapters.ollama_embedding_provider import OllamaEmbeddingProvider
from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.config import find_config, load_config, ConfigError
from recall.searcher import semantic_search
from recall.qdrant_guard import ensure_qdrant

console = Console()


def search(
    query: str = typer.Argument(..., help="Search query"),
    collection: Optional[str] = typer.Option(None, "--in", metavar="PROJECT", help="Restrict to a specific project collection"),
    top_k: int = typer.Option(5, "--top", help="Number of results to return"),
):
    """Search across indexed docs."""
    try:
        config_path = find_config()
        config = load_config(config_path)
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if config.qdrant.host is not None:
        ensure_qdrant(config.qdrant.url)
    vector_store = QdrantVectorStore(config.qdrant)
    embedding_provider = OllamaEmbeddingProvider(config.embedding.model, config.embedding.ollama_host)

    try:
        results = semantic_search(
            query,
            config=config,
            vector_store=vector_store,
            embedding_provider=embedding_provider,
            collection=collection,
            top_k=top_k,
        )
    finally:
        vector_store.close()

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    for r in results:
        header = Text()
        header.append(f"{r.collection}", style="bold cyan")
        header.append(f" · {r.source}", style="dim")
        header.append(f" · score: {r.score:.2f}", style="dim green")
        console.print(Panel(r.text[:500], title=header, border_style="dim"))
