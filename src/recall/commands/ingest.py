from __future__ import annotations

from typing import Any, Optional
import typer
from rich.console import Console
from rich.progress import track

from recall.config import find_config, load_config, ConfigError
from recall.indexer import index_project
from recall.qdrant_guard import ensure_qdrant

console = Console()


def _run_local_ingest(*, mode: str, params: dict[str, Any], _console=None) -> str:
    config_path = find_config()
    config = load_config(config_path)
    ensure_qdrant(config.qdrant.url)
    recreate = bool(params.get("recreate", False))

    if mode == "all":
        projects = list(config.all_projects())
        if only := params.get("only"):
            only_set = set(only)
            projects = [p for p in projects if p.name in only_set]
        elif skip := params.get("skip"):
            skip_set = set(skip)
            projects = [p for p in projects if p.name not in skip_set]
    elif mode == "project":
        projects = [config.project(params["project"])]
    elif mode == "source":
        projects = list(config.projects_from_source(params["source"]))
    else:
        raise ValueError(f"unknown local ingest mode '{mode}'")

    total_chunks = 0
    indexed = 0
    for p in projects:
        if not p.resolved_path.exists():
            if _console is not None:
                _console.print(f"[yellow]⚠[/yellow] {p.name}: path not found, skipping ({p.path})")
            continue
        count = index_project(p, config=config, recreate=recreate)
        total_chunks += count
        indexed += 1
    return f"{indexed} project(s) indexed, {total_chunks} chunks total"


def ingest(
    project_name: Optional[str] = typer.Argument(None, help="Project name from recall.toml"),
    all_projects: bool = typer.Option(False, "--all", help="Ingest all configured projects"),
    recreate: bool = typer.Option(False, "--recreate", help="Drop and recreate collection before indexing"),
):
    """Index project docs into Qdrant."""
    try:
        if all_projects:
            result = _run_local_ingest(mode="all", params={"recreate": recreate}, _console=console)
        elif project_name:
            result = _run_local_ingest(mode="project", params={"project": project_name, "recreate": recreate}, _console=console)
        else:
            console.print("[yellow]Specify a project name or --all[/yellow]")
            raise typer.Exit(1)
        console.print(f"[green]✓[/green] {result}")
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
