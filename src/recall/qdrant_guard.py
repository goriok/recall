from __future__ import annotations

import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import typer
from rich.console import Console

console = Console(stderr=True)

# Installed via `uv tool install`, recall runs from an isolated venv with no
# docker-compose.yml alongside it — bootstrap.sh copies one here so the guard
# always has a fallback regardless of the caller's CWD.
_GLOBAL_COMPOSE_FILE = Path.home() / ".config" / "recall" / "docker-compose.yml"
_HEALTH_TIMEOUT = 15  # seconds to wait for Qdrant to become ready
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _can_autostart(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS


def ensure_qdrant(qdrant_url: str, api_key: str | None = None) -> None:
    """Ensure Qdrant is reachable, starting it via Docker Compose only for a local http host."""
    if _is_reachable(qdrant_url, api_key):
        return

    if not _can_autostart(qdrant_url):
        console.print(f"[red]Error:[/red] Qdrant at {qdrant_url} is not reachable.")
        raise typer.Exit(1)

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

    if not _wait_until_ready(qdrant_url, api_key):
        console.print("[red]Error:[/red] Qdrant started but did not become ready in time.")
        raise typer.Exit(1)

    console.print("[green]✓[/green] Qdrant ready.")


def _is_reachable(url: str, api_key: str | None = None) -> bool:
    headers = {"api-key": api_key} if api_key else {}
    try:
        r = httpx.get(f"{url}/healthz", headers=headers, timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _wait_until_ready(url: str, api_key: str | None = None, timeout: int = _HEALTH_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_reachable(url, api_key):
            return True
        time.sleep(0.5)
    return False


def _find_compose_file() -> Path | None:
    # Walk up from CWD looking for docker-compose.yml in a recall project
    # (developing recall itself, or a project that vendors its own compose file)
    for directory in [Path.cwd(), *Path.cwd().parents]:
        candidate = directory / "docker-compose.yml"
        if candidate.exists() and (directory / "recall.toml").exists():
            return candidate
    # Fallback: the copy bootstrap.sh placed in the global config dir —
    # always present regardless of where `recall`/`recall-mcp` is invoked from.
    if _GLOBAL_COMPOSE_FILE.exists():
        return _GLOBAL_COMPOSE_FILE
    return None
