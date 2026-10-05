from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from recall.qdrant_service import QdrantService, QdrantServiceError

console = Console()


def _probe_mcp() -> str:
    return _run_mcp_initialize()


def _run_mcp_initialize() -> str:
    mcp_bin = Path(sys.executable).parent / "recall-mcp"
    msg = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "healthcheck", "version": "1"}},
    })
    result = subprocess.run([str(mcp_bin)], input=msg + "\n", capture_output=True, text=True, timeout=5)
    return json.loads(result.stdout.splitlines()[0])["result"]["serverInfo"]["version"]


def _service() -> QdrantService:
    return QdrantService()


def _fail(exc: QdrantServiceError) -> None:
    console.print(f"[red]Error:[/red] {exc}")
    raise typer.Exit(1)


def server_start() -> None:
    """Start a local Qdrant (a Podman container on 127.0.0.1) and wait until it answers."""
    service = _service()
    try:
        how = service.start()
    except QdrantServiceError as exc:
        _fail(exc)
    if how == "already-running":
        console.print(f"[yellow]Qdrant already running[/yellow] at {service.spec.url}")
        return
    console.print(f"[green]✓[/green] Qdrant ready at {service.spec.url} ({how})")
    if not service.autostart_installed():
        console.print("[dim]It will not return after a reboot — run [bold]recall server enable[/bold] for that.[/dim]")


def server_stop() -> None:
    """Stop the local Qdrant (its data is kept)."""
    service = _service()
    try:
        how = service.stop()
    except QdrantServiceError as exc:
        _fail(exc)
    if how == "not-running":
        console.print("[yellow]Qdrant was not running[/yellow]")
        return
    console.print("[green]✓[/green] Qdrant stopped")
    if how == "service":
        console.print("[dim]Autostart is still enabled: it comes back at the next boot or login.[/dim]")


def server_restart() -> None:
    """Restart the local Qdrant."""
    service = _service()
    try:
        service.restart()
    except QdrantServiceError as exc:
        _fail(exc)
    console.print(f"[green]✓[/green] Qdrant restarted at {service.spec.url}")


def server_enable(
    linger: bool = typer.Option(True, "--linger/--no-linger", help="Also enable lingering so it starts at boot, before login"),
) -> None:
    """Keep Qdrant running across reboots with a systemd user service (Linux)."""
    service = _service()
    try:
        notes = service.enable(linger=linger)
    except QdrantServiceError as exc:
        _fail(exc)
    for note in notes:
        console.print(f"[green]✓[/green] {note}")
    console.print(f"[dim]Check with [bold]recall server status[/bold]; undo with [bold]recall server disable[/bold].[/dim]")


def server_disable() -> None:
    """Remove the systemd user service. The data volume is kept."""
    service = _service()
    try:
        notes = service.disable()
    except QdrantServiceError as exc:
        _fail(exc)
    for note in notes:
        console.print(f"[green]✓[/green] {note}")


def server_status() -> None:
    """Show Qdrant, its autostart and recall-mcp health."""
    service = _service()
    try:
        status = service.status()
    except QdrantServiceError as exc:
        _fail(exc)
    if status.reachable:
        console.print(f"[green]●[/green] Qdrant reachable at {service.spec.url}")
    else:
        console.print("[red]●[/red] Qdrant unreachable — run [bold]recall server start[/bold]")
    console.print(f"  container {service.spec.name}: {status.container}")
    if status.legacy_container:
        console.print(f"  [yellow]old compose container recall_qdrant_1 is {status.legacy_container}[/yellow] (remove it with: podman rm -f recall_qdrant_1)")
    if service.autostart_installed():
        state = "active" if status.autostart_active else "inactive"
        console.print(f"  autostart: enabled={status.autostart_enabled} ({state}), lingering={status.linger}")
    else:
        console.print("  autostart: off — [bold]recall server enable[/bold] makes it survive reboots")

    try:
        console.print(f"[green]●[/green] recall-mcp v{_probe_mcp()} responds to MCP protocol")
    except Exception as e:
        console.print(f"[red]●[/red] recall-mcp not responding: {e}")


def server_logs(
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(50, "--tail", help="Number of lines to show"),
) -> None:
    """Show the Qdrant container logs."""
    try:
        code = _service().logs(tail=tail, follow=follow)
    except QdrantServiceError as exc:
        _fail(exc)
    if code != 0:
        raise typer.Exit(code)
