import typer
from recall.commands.ingest import ingest
from recall.commands.search import search
from recall.commands.collections import collections_list, collections_drop
from recall.commands.server import server_start, server_stop, server_restart, server_status, server_logs

app = typer.Typer(name="recall", help="Local semantic search over your project docs.")

collections_app = typer.Typer(help="Manage Qdrant collections.")
app.add_typer(collections_app, name="collections")
collections_app.command("list")(collections_list)
collections_app.command("drop")(collections_drop)

server_app = typer.Typer(help="Manage the recall-mcp background process.")
app.add_typer(server_app, name="server")
server_app.command("start")(server_start)
server_app.command("stop")(server_stop)
server_app.command("restart")(server_restart)
server_app.command("status")(server_status)
server_app.command("logs")(server_logs)

app.command("ingest")(ingest)
app.command("search")(search)

if __name__ == "__main__":
    app()
