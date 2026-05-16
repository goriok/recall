from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx
import typer
from rich.console import Console

console = Console()

# docker-compose.yml lives next to recall.toml (project root)
_COMPOSE_FILE = Path(__file__).parent.parent.parent / "docker-compose.yml"
_HEALTH_TIMEOUT = 15  # seconds to wait for Qdrant to become ready


def ensure_qdrant(qdrant_url: str) -> None:
    """Ensure Qdrant is reachable, starting it via Docker Compose if needed."""
    if _is_reachable(qdrant_url):
        return

    console.print("[dim]Qdrant not running — starting via Docker Compose...[/dim]")

    compose_file = _find_compose_file()
    if compose_file is None:
        console.print(
            "[red]Error:[/red] docker-compose.yml not found. "
            "Run [bold]docker compose up -d[/bold] manually from the recall project directory."
        )
        raise typer.Exit(1)

    try:
        subprocess.run(
            ["podman", "compose", "-f", str(compose_file), "up", "-d"],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        console.print("[red]Error:[/red] Podman not found. Install Podman and try again.")
        raise typer.Exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Failed to start Qdrant:\n{e.stderr.decode()}")
        raise typer.Exit(1)

    if not _wait_until_ready(qdrant_url):
        console.print("[red]Error:[/red] Qdrant started but did not become ready in time.")
        raise typer.Exit(1)

    console.print("[green]✓[/green] Qdrant ready.")


def _is_reachable(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/healthz", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _wait_until_ready(url: str, timeout: int = _HEALTH_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_reachable(url):
            return True
        time.sleep(0.5)
    return False


def _find_compose_file() -> Path | None:
    # Walk up from CWD looking for docker-compose.yml in a recall project
    for directory in [Path.cwd(), *Path.cwd().parents]:
        candidate = directory / "docker-compose.yml"
        if candidate.exists() and (directory / "recall.toml").exists():
            return candidate
    # Fallback: alongside this package
    if _COMPOSE_FILE.exists():
        return _COMPOSE_FILE
    return None
