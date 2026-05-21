from __future__ import annotations

from typing import Any, Optional
import typer
from rich.console import Console

from recall.config import find_config, load_config, ConfigError
from recall.confluence.client import ConfluenceClient
from recall.confluence.config import load_confluence_config
from recall.confluence.indexer import index_confluence_pages
from recall.qdrant_guard import ensure_qdrant

console = Console()


def _run_confluence_ingest(
    *,
    mode: str,
    params: dict[str, Any],
    _console: Optional[Console] = None,
) -> str:
    """Core ingest logic shared by CLI and scheduler. Returns a status string."""
    out = _console or Console(quiet=True)

    config_path = find_config()
    config = load_config(config_path)
    confluence_cfg = load_confluence_config(config_path)

    ensure_qdrant(config.qdrant.url)
    client = ConfluenceClient(confluence_cfg)

    collection = params.get("collection")
    recreate = bool(params.get("recreate", False))

    if mode == "page":
        page_id = params["page_id"]
        col = collection or f"confluence-page-{page_id}"
        out.print(f"[dim]Fetching page {page_id} and children...[/dim]")
        root = client.get_page(page_id)
        children = client.get_children(page_id)
        pages = [root, *children]
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        out.print(f"[green]✓[/green] confluence/page-{page_id}: {count} chunks indexed into [bold]{col}[/bold]")
        return f"{count} chunks indexed into {col}"

    elif mode == "folder":
        folder_id = params["folder_id"]
        col = collection or f"confluence-folder-{folder_id}"
        out.print(f"[dim]Fetching pages under folder {folder_id}...[/dim]")
        pages = client.get_folder_children(folder_id)
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        out.print(f"[green]✓[/green] confluence/folder-{folder_id}: {count} chunks indexed into [bold]{col}[/bold]")
        return f"{count} chunks indexed into {col}"

    elif mode == "space":
        space = params["space"]
        col = collection or f"confluence-{space.lower()}"
        out.print(f"[dim]Fetching pages from space {space}...[/dim]")
        pages = client.get_space_pages(space)
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        out.print(f"[green]✓[/green] confluence/{space}: {count} chunks indexed into [bold]{col}[/bold]")
        return f"{count} chunks indexed into {col}"

    elif mode == "label":
        label = params["label"]
        col = collection or f"confluence-label-{label}"
        out.print(f"[dim]Fetching pages with label '{label}'...[/dim]")
        pages = client.get_pages_by_label(label)
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        out.print(f"[green]✓[/green] confluence/label-{label}: {count} chunks indexed into [bold]{col}[/bold]")
        return f"{count} chunks indexed into {col}"

    elif mode == "all":
        col = collection or "confluence-all"
        out.print("[dim]Fetching all accessible pages...[/dim]")
        pages = client.get_all_pages()
        count = index_confluence_pages(pages, collection=col, config=config, recreate=recreate)
        out.print(f"[green]✓[/green] confluence/all: {count} chunks indexed into [bold]{col}[/bold]")
        return f"{count} chunks indexed into {col}"

    else:
        raise ValueError(f"unknown ingest mode '{mode}'")


def ingest_confluence(
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (e.g. ENG)"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Index page and all its children"),
    folder_id: Optional[str] = typer.Option(None, "--folder-id", help="Index all pages under a Confluence folder"),
    label: Optional[str] = typer.Option(None, "--label", help="Index all pages with this label"),
    all_pages: bool = typer.Option(False, "--all", help="Index all accessible pages"),
    collection: Optional[str] = typer.Option(None, "--collection", help="Qdrant collection name"),
    recreate: bool = typer.Option(False, "--recreate", help="Drop and recreate collection before indexing"),
):
    """Index Confluence pages into Qdrant."""
    if not any([space, page_id, folder_id, label, all_pages]):
        console.print("[yellow]Specify at least one of: --space, --page-id, --folder-id, --label, --all[/yellow]")
        raise typer.Exit(1)

    params: dict[str, Any] = {}
    if collection:
        params["collection"] = collection
    if recreate:
        params["recreate"] = True

    if space:
        params["space"] = space
        mode = "space"
    elif page_id:
        params["page_id"] = page_id
        mode = "page"
    elif folder_id:
        params["folder_id"] = folder_id
        mode = "folder"
    elif label:
        params["label"] = label
        mode = "label"
    else:
        mode = "all"

    try:
        _run_confluence_ingest(mode=mode, params=params, _console=console)
    except (ConfigError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
