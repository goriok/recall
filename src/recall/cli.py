import typer
from recall.commands.ingest import ingest
from recall.commands.search import search

app = typer.Typer(name="recall", help="Local semantic search over your project docs.")

app.command("ingest")(ingest)
app.command("search")(search)

if __name__ == "__main__":
    app()
