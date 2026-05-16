import typer
from recall.commands.ingest import ingest
from recall.commands.ingest_confluence import ingest_confluence
from recall.commands.search import search
from recall.commands.collections import collections_list, collections_drop

app = typer.Typer(name="recall", help="Local semantic search over your project docs.")

collections_app = typer.Typer(help="Manage Qdrant collections.")
app.add_typer(collections_app, name="collections")
collections_app.command("list")(collections_list)
collections_app.command("drop")(collections_drop)

app.command("ingest")(ingest)
app.command("ingest-confluence")(ingest_confluence)
app.command("search")(search)

if __name__ == "__main__":
    app()
