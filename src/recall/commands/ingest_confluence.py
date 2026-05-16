from __future__ import annotations

from typing import Optional
import typer
from rich.console import Console

from recall.config import find_config, load_config, ConfigError
from recall.confluence.client import ConfluenceClient
from recall.confluence.config import load_confluence_config
from recall.confluence.indexer import index_confluence_pages
from recall.qdrant_guard import ensure_qdrant

console = Console()


def ingest_confluence(
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (e.g. ENG)"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Index page and all its children"),
    label: Optional[str] = typer.Option(None, "--label", help="Index all pages with this label"),
    all_pages: bool = typer.Option(False, "--all", help="Index all accessible pages"),
    collection: Optional[str] = typer.Option(None, "--collection", help="Qdrant collection name (default: confluence-<space>)"),
    recreate: bool = typer.Option(False, "--recreate", help="Drop and recreate collection before indexing"),
):
    """Index Confluence pages into Qdrant."""
    if not any([space, page_id, label, all_pages]):
        console.print("[yellow]Specify at least one of: --space, --page-id, --label, --all[/yellow]")
        raise typer.Exit(1)

    try:
        config_path = find_config()
        config = load_config(config_path)
        confluence_cfg = load_confluence_config(config_path)
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    ensure_qdrant(config.qdrant.url)

    client = ConfluenceClient(confluence_cfg)

    if space:
        col = collection or f"confluence-{space.lower()}"
        console.print(f"[dim]Fetching pages from space {space}...[/dim]")
        pages = client.get_space_pages(space)
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        console.print(f"[green]✓[/green] confluence/{space}: {count} chunks indexed into [bold]{col}[/bold]")

    elif page_id:
        col = collection or f"confluence-page-{page_id}"
        console.print(f"[dim]Fetching page {page_id} and children...[/dim]")
        root = client.get_page(page_id)
        children = client.get_children(page_id)
        pages = [root, *children]
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        console.print(f"[green]✓[/green] confluence/page-{page_id}: {count} chunks indexed into [bold]{col}[/bold]")

    elif label:
        col = collection or f"confluence-label-{label}"
        console.print(f"[dim]Fetching pages with label '{label}'...[/dim]")
        pages = client.get_pages_by_label(label)
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        console.print(f"[green]✓[/green] confluence/label-{label}: {count} chunks indexed into [bold]{col}[/bold]")

    elif all_pages:
        col = collection or "confluence-all"
        console.print("[dim]Fetching all accessible pages...[/dim]")
        pages = client.get_all_pages()
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        console.print(f"[green]✓[/green] confluence/all: {count} chunks indexed into [bold]{col}[/bold]")
