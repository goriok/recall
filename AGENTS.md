# AGENTS.md — recall

Local semantic search over project documentation. RAG pipeline: markdown → chunks → Ollama embeddings → Qdrant → MCP tool exposed to Claude Code and opencode.

---

## Tech Stack

- **Python 3.12+** — Typer CLI, Rich output, httpx, FastMCP (stdio)
- **Qdrant** — embedded by default (`qdrant-client` local mode, on-disk at `~/.local/share/recall/qdrant`, no server to run); optional server mode (`podman compose up -d`, port 6333) for concurrent access from multiple processes — see `docs/madrs/MADR-002-embedded-qdrant-by-default.md`
- **Ollama** — local embeddings, model `nomic-embed-text` (768 dims)
- **uv** — install via `uv tool install --from . recall`

## Architecture

Hexagonal (ports & adapters) — see `docs/madrs/MADR-001-hexagonal-ports-for-vector-store-and-embedding.md`:
- `core/interfaces.py` — `VectorStore`, `EmbeddingProvider` ports (`Protocol`)
- `adapters/` — `QdrantVectorStore`, `OllamaEmbeddingProvider`, the only implementations today
- `indexer.py`, `searcher.py` receive ports injected, never instantiate the concrete client themselves

## Key Commands

```bash
# install
uv tool install --from . recall            # installs recall + recall-mcp to PATH
./bootstrap.sh                             # full first-time setup (uv, ollama, config)

# ingest
recall ingest                              # ingest explicit projects from recall.toml
recall ingest --all                        # ingest all auto-discovered projects
recall ingest --project mcx-companion      # single project

# search
recall search "authentication flow"
recall search "auth" --project mcx-companion --top-k 10

# dev / test
uv run pytest                              # full suite
uv run pytest tests/test_chunker.py       # single file
uv run pytest --cov                       # with coverage (fails below 90%)
```

## Configuration

Config lookup order (first found wins):
1. `recall.toml` — walk CWD upward
2. `~/.config/recall/recall.toml` — global fallback

Two modes coexist in the same file:
- `[[projects]]` — explicit entries with custom path/collection/glob
- `[[sources]]` — auto-discover: every subdir with matching files becomes a collection

`[qdrant]` defaults to embedded mode (`path`, default `~/.local/share/recall/qdrant`). Set `host`/`port` instead for server mode.

## Non-Obvious Patterns

- **Chunk IDs are deterministic** — SHA-256 of `source::heading::index` enables upsert idempotency (re-ingest is safe).
- **Embedded Qdrant holds an exclusive file lock** per `path` for as long as the client is open — only one process at a time. `mcp_server.py` builds the adapters once per process (module-level singleton) and reuses them; CLI commands `close()` explicitly in `finally` instead of relying on the GC.
- **Qdrant auto-starts in server mode only** — `qdrant_guard.ensure_qdrant()` calls `podman compose up -d` if port 6333 is unreachable; walks CWD upward to find `docker-compose.yml`, falling back to `~/.config/recall/docker-compose.yml` (placed there by `bootstrap.sh`). Not invoked at all when `[qdrant].host` is unset (embedded mode).
- **Auto-discover precedence** — explicit `[[projects]]` names shadow auto-discovered dirs with the same name.
- **Ollama client init** — use `ollama.Client(host=config.ollama_host)`, not `options={"host": ...}` (wrong API).
- **Qdrant query API** — use `client.query_points()`, not deprecated `client.search()` (removed in qdrant-client ≥ 1.9).
- **CLI registration** — commands registered with `app.command("name")(fn)` directly; avoid `app.add_typer()` which causes double-routing.

## Code Style

- No comments unless the WHY is non-obvious.
- No docstrings beyond one short line max.
- Dataclasses for config/data objects; no Pydantic.
- All public functions typed; `from __future__ import annotations` at top.

## Testing Rules

- TDD: write failing test first, then implement.
- No real network calls in tests — use `tests/fakes.py` (`FakeVectorStore`, `FakeEmbeddingProvider`) for anything touching `VectorStore`/`EmbeddingProvider`; mock at the application boundary (e.g. `index_project`, `semantic_search`) for command/MCP-layer tests.
- Patch at the import site of the consumer, not the definition site.
- Coverage gate: 90% — enforced by `pytest --cov` (informational; the suite currently sits below this on unit tests alone — integration paths that exercise the real adapters aren't covered by the mocked suite).

## Boundaries

### Always (no approval needed)
- Edit files in `src/recall/`, `tests/`, `*.toml`, `*.sh`, `.opencode/commands/`
- Run `uv run pytest`, `recall --help`, `recall search`

### Ask First
- `recall ingest` or `recall ingest --all` (touches Qdrant collections)
- `podman compose` commands (server mode only)
- Changes to `~/.config/recall/recall.toml`

### Never
- Hardcode usernames, absolute paths, or tokens in source files
- Commit `.env` files or files containing real credentials
- Modify `uv.lock` manually
