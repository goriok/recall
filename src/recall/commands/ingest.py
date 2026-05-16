from __future__ import annotations

from typing import Optional
import typer
from rich.console import Console
from rich.progress import track

from recall.config import find_config, load_config, ConfigError
from recall.indexer import index_project
from recall.qdrant_guard import ensure_qdrant

console = Console()


def ingest(
    project_name: Optional[str] = typer.Argument(None, help="Project name from recall.toml"),
    all_projects: bool = typer.Option(False, "--all", help="Ingest all configured projects"),
    recreate: bool = typer.Option(False, "--recreate", help="Drop and recreate collection before indexing"),
):
    """Index project docs into Qdrant."""
    try:
        config_path = find_config()
        config = load_config(config_path)
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    ensure_qdrant(config.qdrant.url)

    if all_projects:
        projects = config.all_projects()
    elif project_name:
        try:
            projects = [config.project(project_name)]
        except ConfigError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        console.print("[yellow]Specify a project name or --all[/yellow]")
        raise typer.Exit(1)

    for project in track(projects, description="Indexing..."):
        if not project.resolved_path.exists():
            console.print(f"[yellow]⚠[/yellow] {project.name}: path not found, skipping ({project.path})")
            continue
        count = index_project(project, config=config, recreate=recreate)
        console.print(f"[green]✓[/green] {project.name}: {count} chunks indexed")
