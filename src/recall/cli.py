import typer
from recall.commands.ingest import ingest
from recall.commands.ingest_confluence import ingest_confluence
from recall.commands.search import search

app = typer.Typer(name="recall", help="Local semantic search over your project docs.")

app.command("ingest")(ingest)
app.command("ingest-confluence")(ingest_confluence)
app.command("search")(search)

if __name__ == "__main__":
    app()
