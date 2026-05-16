# AGENTS.md — recall

Local semantic search over project documentation. RAG pipeline: markdown → chunks → Ollama embeddings → Qdrant → MCP tool exposed to Claude Code and opencode.

---

## Tech Stack

- **Python 3.12+** — Typer CLI, Rich output, httpx, FastMCP (stdio)
- **Qdrant** — local vector store via `podman compose up -d` (port 6333)
- **Ollama** — local embeddings, model `nomic-embed-text` (768 dims)
- **uv** — install via `uv tool install --from . recall`

## Key Commands

```bash
# install
uv tool install --from . recall            # installs recall + recall-mcp to PATH
./bootstrap.sh                             # full first-time setup (uv, ollama, config)

# ingest
recall ingest                              # ingest explicit projects from recall.toml
recall ingest --all                        # ingest all auto-discovered projects
recall ingest --project mcx-companion      # single project

# ingest confluence
recall ingest-confluence --space ENG       # entire space
recall ingest-confluence --page-id 123456  # page + all children
recall ingest-confluence --label architecture

# search
recall search "authentication flow"
recall search "auth" --project mcx-companion --top-k 10

# dev / test
uv run pytest                              # all 59 tests
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

Secrets in `[confluence]` use `{env:VAR_NAME}` interpolation — never hardcode tokens.

## Non-Obvious Patterns

- **Chunk IDs are deterministic** — SHA-256 of `source::heading::index` enables upsert idempotency (re-ingest is safe).
- **Qdrant auto-starts** — `qdrant_guard.ensure_qdrant()` calls `podman compose up -d` if port 6333 is unreachable; walks CWD upward to find `docker-compose.yml`.
- **Auto-discover precedence** — explicit `[[projects]]` names shadow auto-discovered dirs with the same name.
- **Ollama client init** — use `ollama.Client(host=config.ollama_host)`, not `options={"host": ...}` (wrong API).
- **Qdrant query API** — use `client.query_points()`, not deprecated `client.search()` (removed in qdrant-client ≥ 1.9).
- **Confluence Cloud vs Server** — Cloud uses basic auth (email + token); Server/DC uses Bearer token header. Detected via `"atlassian.net" in url`.
- **CLI registration** — commands registered with `app.command("name")(fn)` directly; avoid `app.add_typer()` which causes double-routing.

## Code Style

- No comments unless the WHY is non-obvious.
- No docstrings beyond one short line max.
- Dataclasses for config/data objects; no Pydantic.
- All public functions typed; `from __future__ import annotations` at top.

## Testing Rules

- TDD: write failing test first, then implement.
- No real network calls in tests — mock `_get`, `embed_batch`, `QdrantClient`, `httpx`.
- Patch at the import site of the consumer, not the definition site (e.g. `recall.commands.ingest_confluence.ConfluenceClient`).
- `embed_batch` mock must use `side_effect=lambda texts, config: [[0.1]*768 for _ in texts]`.
- Coverage gate: 90% — enforced by `pytest --cov`.

## Boundaries

### Always (no approval needed)
- Edit files in `src/recall/`, `tests/`, `*.toml`, `*.sh`, `.opencode/commands/`
- Run `uv run pytest`, `recall --help`, `recall search`

### Ask First
- `recall ingest` or `recall ingest --all` (touches Qdrant collections)
- `podman compose` commands
- Changes to `~/.config/recall/recall.toml`

### Never
- Hardcode usernames, absolute paths, or tokens in source files
- Commit `.env` files or files containing real credentials
- Modify `uv.lock` manually
