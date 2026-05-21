from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from recall.config import find_config, load_config, ConfigError
from recall.scheduler.config import parse_schedules, ScheduleEntry, ScheduleConfigError
from recall.scheduler.cron import next_fire
from recall.scheduler.gchat import GChatNotifier
from recall.scheduler.jobs import dispatch
from recall.scheduler.worker import run_schedule_loop

console = Console()


def _load_entries() -> list[ScheduleEntry]:
    config_path = find_config()
    with open(config_path, "rb") as f:
        import tomllib
        data = tomllib.load(f)
    try:
        return parse_schedules(data)
    except ScheduleConfigError as e:
        raise ConfigError(str(e)) from e


def _log_path(name: str) -> Path:
    log_dir = Path.home() / ".cache" / "recall" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{name}.log"


def scheduler_list():
    """List configured ingest schedules and their next fire time."""
    try:
        entries = _load_entries()
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not entries:
        console.print("[dim]No schedules configured. Add [[schedules]] to recall.toml.[/dim]")
        return

    now = datetime.now(tz=timezone.utc)
    table = Table(show_header=True)
    table.add_column("name", style="bold")
    table.add_column("job")
    table.add_column("cron")
    table.add_column("next fire (UTC)")

    for entry in entries:
        nxt = next_fire(entry.cron, now)
        table.add_row(entry.name, entry.job, entry.cron, nxt.strftime("%Y-%m-%d %H:%M:%S"))

    console.print(table)


def scheduler_trigger(name: str = typer.Argument(..., help="Schedule name to trigger now")):
    """Trigger a named ingest schedule immediately (without waiting for its cron)."""
    try:
        entries = _load_entries()
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    entry = next((e for e in entries if e.name == name), None)
    if entry is None:
        names = [e.name for e in entries]
        console.print(f"[red]Unknown schedule '{name}'. Available:[/red] {names}")
        raise typer.Exit(1)

    notifier = GChatNotifier()

    async def run():
        await notifier.on_start(entry.name)
        import time
        t0 = time.monotonic()
        try:
            output = await asyncio.to_thread(dispatch, entry)
            duration_ms = int((time.monotonic() - t0) * 1000)
            console.print(f"[green]✓[/green] {output}")
            await notifier.on_result(entry.name, duration_ms=duration_ms, output=output)
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            await notifier.on_error(entry.name, error=exc)
            raise typer.Exit(1)

    asyncio.run(run())


def scheduler_run():
    """Run the ingest scheduler daemon (blocks until SIGTERM/SIGINT)."""
    try:
        entries = _load_entries()
    except ConfigError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not entries:
        console.print("[dim]No schedules configured. Add [[schedules]] to recall.toml.[/dim]")
        raise typer.Exit(0)

    console.print(f"[bold]recall scheduler[/bold] starting with {len(entries)} job(s)")
    for e in entries:
        nxt = next_fire(e.cron, datetime.now(tz=timezone.utc))
        console.print(f"  • {e.name} [{e.job}] — next: {nxt.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    notifier = GChatNotifier()
    stop_event = asyncio.Event()

    async def main():
        loop = asyncio.get_running_loop()

        def _handle_shutdown():
            console.print("\n[yellow]Shutting down...[/yellow]")
            stop_event.set()

        loop.add_signal_handler(signal.SIGTERM, _handle_shutdown)
        loop.add_signal_handler(signal.SIGINT, _handle_shutdown)

        callbacks = {
            "on_start": notifier.on_start,
            "on_result": notifier.on_result,
            "on_error": notifier.on_error,
        }

        tasks = [
            asyncio.create_task(run_schedule_loop(e, callbacks=callbacks, stop_event=stop_event))
            for e in entries
        ]

        await stop_event.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        console.print("[dim]Scheduler stopped.[/dim]")

    asyncio.run(main())
