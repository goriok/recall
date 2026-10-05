# AGENTS.md — recall

Semantic search over project documentation and source code. RAG pipeline: markdown/code → chunks (lines, symbols, breadcrumb) → embeddings (Ollama or a remote OpenAI-compatible endpoint) → Qdrant → MCP tools exposed to Claude Code and opencode.

---

## Tech Stack

- **Python 3.12+** — Typer CLI, Rich output, httpx, FastMCP (stdio)
- **Qdrant** — embedded by default (`qdrant-client` local mode, on-disk at `~/.local/share/recall/qdrant`, no server to run); optional server mode (`recall server start`, port 6333) for concurrent access from multiple processes — see `docs/madrs/MADR-002-embedded-qdrant-by-default.md`
- **Embeddings** — Ollama (`nomic-embed-text`, 768 dims; truncates input at `max_chars`, default 1500) or a remote OpenAI-compatible endpoint (for example `nomic-embed-text-v1-5`, 768 dims, batch ≤ 32), configured per project and, preferably, through `RECALL_EMBEDDING_*` in `~/.config/recall/.env`
- **uv** — install via `uv tool install --from . recall`

## Architecture

Hexagonal (ports & adapters) — see `docs/madrs/MADR-001-hexagonal-ports-for-vector-store-and-embedding.md`:
- `core/interfaces.py` — `VectorStore`, `EmbeddingProvider` ports (`Protocol`)
- `adapters/` — `QdrantVectorStore`, `OllamaEmbeddingProvider`, `OpenAIEmbeddingProvider`; `embeddings.ProviderResolver` builds one provider per distinct embedding config
- `indexer.py`, `searcher.py` receive ports injected, never instantiate the concrete client themselves

## Key Commands

```bash
# install
uv tool install --from . recall            # installs recall + recall-mcp to PATH
./bootstrap.sh                             # full first-time setup (uv, ollama, config)

# ingest
recall ingest --all                        # all projects: [[projects]], [[sources]] topics and [[repos]]
recall ingest mcx-companion                # single project or repo by name
recall ingest mcx-companion --recreate     # rebuild; required after changing the embedding model

# search
recall search "authentication flow"
recall search "auth" --in mcx-companion --top 10

# dev / test (use `python -m pytest`; the `pytest` shim is not on the uv run PATH)
uv sync --group dev
uv run python -m pytest                    # unit suite (integration and remote markers deselected)
uv run python -m pytest --cov              # with coverage (gate 90%)
RECALL_TEST_QDRANT_URL=http://localhost:16333 uv run python -m pytest -m integration   # needs a Qdrant server
RECALL_TEST_EMBEDDING_URL=<url> RECALL_EMBEDDING_API_KEY=<key> uv run python -m pytest -m remote   # needs an embeddings endpoint
```

## Configuration

Config lookup order (first found wins):
1. `recall.toml` — walk CWD upward
2. `~/.config/recall/recall.toml` — global fallback

Three kinds of entry coexist in the same file:
- `[[projects]]` — explicit entries with custom path/collection/glob
- `[[sources]]` — auto-discover: every subdir with matching files becomes a collection (docs; `file_path` is relative to `repo_root`, default `root.parent`)
- `[[repos]]` — source code: one `code.<name>` collection per repo, optional Graphify enrichment

Each entry may carry its own `embedding` table overriding the global `[embedding]`.

`[qdrant]` defaults to embedded mode (`path`, default `~/.local/share/recall/qdrant`). Set `host`/`port` instead for server mode.

## Plugin packaging

Skills live only in `skills/<name>/SKILL.md` (today `recall-search`, `recall-code`, `recall-ingest`) and are shared by every host. Add a skill only for a distinct trigger and workflow — each one costs context in every installation; contributor-only procedures (adding a tree-sitter language, cutting a release) belong in `CONTRIBUTING.md` or a repo-local `.claude/skills/`, not in `skills/`. `tests/test_plugin_packaging.py` checks that the skills mention only real MCP tools and reference only existing skills. Hosts: Claude Code reads them from the plugin root (`.claude-plugin/`), Hermes from the portable package (`plugin.json` + `mcp.json`, Agent Plugins v1) and `agy` through the `plugins/recall/skills` symlink. Keep the version identical in `pyproject.toml`, `.claude-plugin/plugin.json` and `plugin.json` (`tests/test_plugin_packaging.py` enforces it) and validate with `claude plugin validate .`, `hermes plugins validate .` and `agy plugin validate ./plugins/recall`. Hermes filters the environment of MCP servers to a safe set (`HOME` included), which is why the endpoint and key live in `~/.config/recall/.env`, read by `recall` itself, rather than in the host's MCP `env`.

## Non-Obvious Patterns

- **Chunk IDs are stable** — SHA-256 of `repo::file_path::breadcrumb|qualname::k` (`k` = occurrence of the same name in the file); no positional index, so inserting a section or function does not change neighbor IDs. Re-ingest deletes a file's old points (after embedding the new ones) and removes points of deleted files.
- **`text` is raw, `embed_text` is prefixed** — the payload `text` equals source lines `start_line..end_line`; the prefix (breadcrumb or `file:lines symbol`) only goes into the embedding.
- **`recall-meta`** holds one point per collection (`uuid5` of its name, vector `[1.0]`) with `model_id`/`dimensions` (and the Graphify report for repos). Searching a collection built by another model raises `ModelMismatchError`; a collection with no record is treated as legacy `ollama:nomic-embed-text`/768 and rebuilt on the next ingest.
- **A project-local `recall.toml` is untrusted input** (it is found by walking up from CWD). It may only use a remote destination — embeddings `base_url`/`ollama_host` or Qdrant `host` — that the global `.env` (`RECALL_EMBEDDING_BASE_URL`), the global `recall.toml`, its `[security] trusted_hosts` or `RECALL_TRUSTED_HOSTS` already declare, even when no key is involved, and it may only send the `api_key_env` the global file pairs with that host; remote hosts need https when a key is sent. URLs are parsed strictly (`config._endpoint`: no backslash, userinfo, controls or non-ASCII host, and `urllib` and `httpx` must agree). Otherwise a cloned repo could ship the indexed content, or any env var, to its own server.
- **`recall ingest --prune` is deliberately conservative** — it ignores sources whose directory is missing or that discover no topics, never touches `recall-meta` or `code.*`, asks before dropping (`--yes` skips it) and does nothing if a project failed in the same run.
- **The denylist is case-insensitive and checks symlink targets**, so `.ENV`, `Credentials.json` and `notes.txt -> .env` are not indexed.
- **Remote embedding endpoints accept at most 32 inputs per request** and returns 400 above that; 404 means wrong model name. Only 429/5xx are retried. Never log `request.headers` — errors are re-raised sanitized.
- **Go / JS / Rust chunking is tree-sitter, an optional extra** (`recall[code]`; also in the `dev` group so tests run against the real grammars). Symbol names are qualified (`Server.Start` from the Go receiver, `Calculator.run`, `Cache.lookup` from `impl Cache`; trait impls get a header named `Cache (impl Store)`). Doc comments, JSDoc and Rust `#[attributes]` that sit directly above a symbol (no blank line, first thing on their line) belong to its chunk; `def_line` is the declaration line without them, which is what Graphify reports. Files with unusual line separators (`\f`, lone `\r`, U+2028) fall back to windows because tree-sitter rows would not match `splitlines()`.
- **Graphify is optional** — `graphify update --force` + `god-nodes --json` run as subprocesses with `GRAPHIFY_OUT` outside the repo and `cwd=<root>`; failures degrade to no graph metadata. `source_location` is `L<n>` of the `def`/`class` line, never the decorator, so chunks match on `def_line`.
- **Embedded Qdrant holds an exclusive file lock** per `path` for as long as the client is open — only one process at a time. `mcp_server.py` builds the adapters once per process (module-level singleton) and reuses them; CLI commands `close()` explicitly in `finally` instead of relying on the GC.
- **Qdrant auto-starts for the local default port only** — `qdrant_guard.ensure_qdrant()` calls `QdrantService.start()` (a `podman run` of `qdrant/qdrant`, no compose file needed) if `http://localhost:6333` is unreachable; any other host, port or https gets an error instead. The container publishes on `127.0.0.1` only, and `recall server enable` installs a systemd user unit (`Restart=always`, `WantedBy=default.target`) plus lingering so it returns after reboots. Data lives in the Podman volume `recall_qdrant_data`, which survives `disable` and container removal; the old compose container `recall_qdrant_1` must be removed before `enable` because it holds the same ports; walks CWD upward to find `docker-compose.yml`, falling back to `~/.config/recall/docker-compose.yml` (placed there by `bootstrap.sh`). Not invoked at all when `[qdrant].host` is unset (embedded mode).
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

- `tests/conftest.py` replaces `qdrant_service._default_run` and `server._probe_mcp` with functions that raise, so a unit test can never start a container or call systemd on the developer's machine; if a test trips it, patch `ensure_qdrant` at the consumer module or pass a fake `run` to `QdrantService`.

- TDD: write failing test first, then implement.
- No real network calls in tests — use `tests/fakes.py` (`FakeVectorStore`, `FakeEmbeddingProvider`) for anything touching `VectorStore`/`EmbeddingProvider`; mock at the application boundary (e.g. `index_project`, `semantic_search`) for command/MCP-layer tests.
- Patch at the import site of the consumer, not the definition site.
- Coverage gate: 90% — enforced by `pytest --cov`. `QdrantVectorStore` is unit-tested against `QdrantClient(":memory:")` via the `client=` parameter; tests marked `integration` (Qdrant server) and `remote` (embeddings endpoint) are deselected by default.

## Boundaries

### Always (no approval needed)
- Edit files in `src/recall/`, `tests/`, `*.toml`, `*.sh`, `.opencode/commands/`
- Run `uv run pytest`, `recall --help`, `recall search`

### Ask First
- `recall ingest` or `recall ingest --all` (touches Qdrant collections)
- `recall server enable` / `disable` (installs or removes a systemd user service and may turn on lingering)
- Changes to `~/.config/recall/recall.toml`

### Never
- Hardcode usernames, absolute paths, or tokens in source files
- Commit `.env` files or files containing real credentials
- Modify `uv.lock` manually
