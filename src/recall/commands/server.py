from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx
import typer
from rich.console import Console

console = Console()

_BUNDLED_COMPOSE = Path(__file__).parent.parent.parent.parent / "docker-compose.yml"


def _compose(*args: str) -> subprocess.CompletedProcess:
    """Run podman compose with the recall docker-compose.yml."""
    cmd = ["podman", "compose", "-f", str(_find_compose()), *args]
    return subprocess.run(cmd, text=True)


def _find_compose() -> Path:
    # walk up from cwd first (user may be inside the project)
    for d in [Path.cwd(), *Path.cwd().parents]:
        candidate = d / "docker-compose.yml"
        if candidate.exists() and (d / "recall.toml").exists():
            return candidate
    # fallback: bundled alongside the package source
    if _BUNDLED_COMPOSE.exists():
        return _BUNDLED_COMPOSE
    console.print("[red]Error:[/red] docker-compose.yml not found. Run from the recall project directory.")
    raise typer.Exit(1)


def _qdrant_health(url: str = "http://localhost:6333") -> bool:
    try:
        r = httpx.get(f"{url}/healthz", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def server_start() -> None:
    """Start Qdrant via podman compose (required by recall-mcp)."""
    if _qdrant_health():
        console.print("[yellow]Qdrant already running[/yellow]")
        raise typer.Exit(0)

    console.print("[dim]Starting Qdrant...[/dim]")
    result = _compose("up", "-d")
    if result.returncode != 0:
        console.print("[red]Error:[/red] failed to start Qdrant")
        raise typer.Exit(1)

    import time
    for _ in range(30):
        if _qdrant_health():
            console.print("[green]✓[/green] Qdrant ready at http://localhost:6333")
            return
        time.sleep(0.5)

    console.print("[red]Error:[/red] Qdrant started but did not become ready in time")
    raise typer.Exit(1)


def server_stop() -> None:
    """Stop Qdrant container."""
    console.print("[dim]Stopping Qdrant...[/dim]")
    result = _compose("down")
    if result.returncode != 0:
        console.print("[red]Error:[/red] failed to stop Qdrant")
        raise typer.Exit(1)
    console.print("[green]✓[/green] Qdrant stopped")


def server_restart() -> None:
    """Restart Qdrant container."""
    console.print("[dim]Restarting Qdrant...[/dim]")
    result = _compose("restart")
    if result.returncode != 0:
        console.print("[red]Error:[/red] failed to restart Qdrant")
        raise typer.Exit(1)
    console.print("[green]✓[/green] Qdrant restarted")


def server_status() -> None:
    """Show Qdrant and recall-mcp health."""
    if _qdrant_health():
        console.print("[green]●[/green] Qdrant reachable at http://localhost:6333")
    else:
        console.print("[red]●[/red] Qdrant unreachable — run [bold]recall server start[/bold]")

    # smoke-test the MCP binary
    mcp_bin = Path(sys.executable).parent / "recall-mcp"
    try:
        import json
        msg = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "healthcheck", "version": "1"}},
        })
        result = subprocess.run(
            [str(mcp_bin)],
            input=msg + "\n",
            capture_output=True,
            text=True,
            timeout=5,
        )
        data = json.loads(result.stdout.splitlines()[0])
        version = data["result"]["serverInfo"]["version"]
        console.print(f"[green]●[/green] recall-mcp v{version} responds to MCP protocol")
    except Exception as e:
        console.print(f"[red]●[/red] recall-mcp not responding: {e}")


def server_logs(
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(50, "--tail", help="Number of lines to show"),
) -> None:
    """Show Qdrant container logs."""
    args = ["logs", f"--tail={tail}"]
    if follow:
        args.append("-f")
    _compose(*args)
