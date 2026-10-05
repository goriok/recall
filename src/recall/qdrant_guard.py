from __future__ import annotations

from urllib.parse import urlparse

import typer
from rich.console import Console

from recall.qdrant_service import QdrantService, QdrantServiceError, ServiceSpec, is_healthy

console = Console(stderr=True)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _can_autostart(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS and parsed.port == ServiceSpec().http_port


def _is_reachable(url: str, api_key: str | None = None) -> bool:
    return is_healthy(url, api_key)


def ensure_qdrant(qdrant_url: str, api_key: str | None = None) -> None:
    """Ensure Qdrant is reachable, starting the local container only for the default local http port."""
    if _is_reachable(qdrant_url, api_key):
        return

    if not _can_autostart(qdrant_url):
        console.print(f"[red]Error:[/red] Qdrant at {qdrant_url} is not reachable.")
        raise typer.Exit(1)

    console.print("[dim]Qdrant not running — starting it...[/dim]")
    try:
        QdrantService().start()
    except QdrantServiceError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    console.print("[green]✓[/green] Qdrant ready.")
