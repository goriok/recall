from __future__ import annotations

from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.config import find_config, load_config, ConfigError
from recall.qdrant_guard import ensure_qdrant

console = Console()


def collections_list():
    """List all Qdrant collections with their vector counts."""
    try:
        config = load_config(find_config())
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if config.qdrant.host is not None:
        ensure_qdrant(config.qdrant.url)
    vector_store = QdrantVectorStore(config.qdrant)

    try:
        cols = vector_store.list_collections()
    finally:
        vector_store.close()

    if not cols:
        console.print("[dim]No collections found.[/dim]")
        return

    table = Table(title="Qdrant Collections")
    table.add_column("Collection", style="bold")
    table.add_column("Vectors", justify="right")

    for col in sorted(cols, key=lambda c: c.name):
        table.add_row(col.name, str(col.points_count))

    console.print(table)


def collections_drop(
    name: Optional[str] = typer.Argument(None, help="Collection name to drop"),
    all_collections: bool = typer.Option(False, "--all", help="Drop ALL collections"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Drop one or all Qdrant collections."""
    try:
        config = load_config(find_config())
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not name and not all_collections:
        console.print("[yellow]Specify a collection name or --all[/yellow]")
        raise typer.Exit(1)

    if config.qdrant.host is not None:
        ensure_qdrant(config.qdrant.url)
    vector_store = QdrantVectorStore(config.qdrant)

    try:
        if all_collections:
            targets = [c.name for c in vector_store.list_collections()]
            if not targets:
                console.print("[dim]No collections to drop.[/dim]")
                return
            label = f"ALL {len(targets)} collections"
        else:
            targets = [name]
            label = f"collection '{name}'"

        if not yes:
            confirm = typer.confirm(f"Drop {label}? This cannot be undone.")
            if not confirm:
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(0)

        for col in targets:
            vector_store.delete_collection(col)
            console.print(f"[red]✗[/red] dropped: {col}")
    finally:
        vector_store.close()
