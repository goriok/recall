# Contributing to recall

## Welcome & Scope

recall is a local RAG tool — contributions that keep it fast, offline, and zero-API-cost are most welcome. Out of scope: cloud-only features, external embedding providers, or anything that adds a hard network dependency to the search hot path.

## Code of Conduct

Be direct, be kind, be constructive. No harassment, no gatekeeping.

## Legal

This project uses the **Developer Certificate of Origin (DCO)**. By signing off your commit (`git commit -s`) you certify that you wrote the code and have the right to submit it under the MIT license. [Full DCO text](https://developercertificate.org/).

## Development Setup

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/), [Ollama](https://ollama.com/download). [Podman](https://podman.io/) + `podman-compose` only needed if you test server mode (`[qdrant] host`/`port`) — embedded mode (the default) needs neither.

```bash
git clone https://github.com/goriok/recall.git
cd recall

# create venv and install dev deps
uv sync --dev

# verify
uv run pytest
```

No Qdrant or Ollama needed to run the test suite — all external calls are mocked.

## Common Commands

```bash
uv run pytest                    # full test suite
uv run pytest tests/test_chunker.py   # single file
uv run pytest --cov              # with coverage report (gate: 90%)
uv tool install --from . recall --force --reinstall   # reinstall CLI after changes
```

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/) — no scope required:

```
feat: add collection_prefix to auto-discovered sources
fix: resolve embedded Qdrant lock leaking across mcp_server calls
test: add coverage for auto-discover with empty dirs
docs: update README quick start
chore: bump qdrant-client to 1.9
```

Sign off every commit:

```bash
git commit -s -m "feat: add label-based Confluence ingest"
```

## Branching Strategy

- `main` — always releasable
- Feature branches: `feat/<short-name>`, `fix/<short-name>`
- PRs target `main` directly (small project, no release branches)

## Pull Request Process

1. Link the issue your PR addresses (or explain why no issue exists)
2. All tests must pass: `uv run pytest`
3. Coverage must not drop below 90%: `uv run pytest --cov`
4. If you change a prompt or tool definition in `mcp_server.py`, include a before/after example of what `search_docs` returns
5. One reviewer approval required before merge

## Testing Requirements

- Write tests before implementation (TDD).
- No real network/disk calls against `VectorStore`/`EmbeddingProvider` — use `tests/fakes.py` (`FakeVectorStore`, `FakeEmbeddingProvider`), not `mock.patch` on `QdrantClient`/`ollama` directly.
- Integration tests (real Qdrant embedded store + Ollama) are not in CI; run them locally with `recall ingest` / `recall search` against a scratch `recall.toml`.
- Coverage gate 90% enforced by `pytest --cov` in CI.

## Code Style

- No comments unless the WHY is non-obvious.
- No multi-line docstrings.
- Dataclasses for data objects; type-annotate all public functions.
- `from __future__ import annotations` at top of every module.
- No `print()` — use `rich.console.Console`.

## Reporting Bugs & Security

- **Bugs:** Open a GitHub Issue with reproduction steps and `uv run pytest -x` output.
- **Security:** Do not open a public issue. Use GitHub's [private security advisory](https://github.com/goriok/recall/security/advisories/new).

## Feature Requests

Open an Issue with the use case and why it can't be solved by configuration. PRs without a linked issue for non-trivial features may be closed.
