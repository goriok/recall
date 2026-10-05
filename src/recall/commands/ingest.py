from __future__ import annotations

from typing import Optional
import typer
from rich.console import Console
from rich.progress import track

from recall.adapters.openai_embedding_provider import EmbeddingProviderError
from recall.adapters.qdrant_vector_store import QdrantVectorStore
from recall.config import Config, ConfigError, find_config, load_config
from recall.discovery import DiscoveryError
from recall.embeddings import ProviderResolver
from recall.indexer import IndexReport, index_project
from recall.meta import ModelMismatchError, delete_meta
from recall.qdrant_guard import ensure_qdrant

console = Console()


def _open_store(config: Config) -> QdrantVectorStore:
    try:
        return QdrantVectorStore(config.qdrant)
    except RuntimeError as exc:
        if "already accessed by another instance" in str(exc):
            console.print(
                "[red]Error:[/red] another process (recall-mcp?) has the embedded Qdrant store open. "
                "Stop it, or switch to a Qdrant server ([qdrant] host/port) for concurrent access."
            )
            raise typer.Exit(1)
        raise


def _orphan_collections(config: Config, vector_store: QdrantVectorStore) -> list[str]:
    known = {p.collection for p in config.all_projects()}
    prefixes = tuple(f"{prefix}." for prefix in config.source_prefixes())
    return sorted(
        c.name for c in vector_store.list_collections() if c.name.startswith(prefixes) and c.name not in known
    )


def ingest(
    project_name: Optional[str] = typer.Argument(None, help="Project name from recall.toml"),
    all_projects: bool = typer.Option(False, "--all", help="Ingest all configured projects"),
    recreate: bool = typer.Option(False, "--recreate", help="Drop and recreate collection before indexing"),
    prune: bool = typer.Option(False, "--prune", help="With --all, also drop collections of topics that no longer exist"),
):
    """Index project docs and code repos into Qdrant."""
    try:
        config_path = find_config()
        config = load_config(config_path)
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if config.qdrant.host is not None:
        ensure_qdrant(config.qdrant.url, config.qdrant.api_key())
    vector_store = _open_store(config)
    resolver = ProviderResolver(config)
    failures = 0

    try:
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
            report = IndexReport()
            try:
                count = index_project(
                    project,
                    config=config,
                    vector_store=vector_store,
                    embedding_provider=resolver.for_project(project),
                    recreate=recreate,
                    report=report,
                )
            except (DiscoveryError, ModelMismatchError, EmbeddingProviderError, ConfigError) as exc:
                console.print(f"[red]✗[/red] {project.name}: {exc}")
                failures += 1
                continue
            console.print(f"[green]✓[/green] {project.name}: {count} chunks indexed")
            if report.removed_files:
                console.print(f"  [dim]removed {report.removed_files} deleted file(s) from the index[/dim]")
            if report.skipped:
                summary = ", ".join(f"{n} {why}" for why, n in sorted(report.skipped.items()))
                console.print(f"  [dim]skipped: {summary}[/dim]")
            if report.graph is False:
                console.print("  [yellow]graph metadata unavailable (graphify missing or failed)[/yellow]")
            for warning in report.warnings:
                console.print(f"  [yellow]⚠[/yellow] {warning}")

        if all_projects:
            for name in _orphan_collections(config, vector_store):
                if prune:
                    vector_store.delete_collection(name)
                    delete_meta(vector_store, name)
                    console.print(f"[red]✗[/red] pruned orphan collection: {name}")
                else:
                    console.print(f"[yellow]⚠[/yellow] orphan collection (topic gone): {name} — use --prune to drop it")
    finally:
        vector_store.close()

    if failures:
        raise typer.Exit(1)
