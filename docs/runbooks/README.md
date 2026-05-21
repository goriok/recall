# recall — Runbooks

Operational guides for running and maintaining recall.

## I need to…

| Goal | Runbook |
|---|---|
| Run the scheduler in Docker (production) | [scheduler-docker.md](scheduler-docker.md) |
| Run the scheduler on the host (dev / no Docker) | [scheduler-host.md](scheduler-host.md) |
| Add or edit a `[[schedules]]` entry | [add-schedule.md](add-schedule.md) |
| Set up Confluence ingestion | [confluence-ingest.md](confluence-ingest.md) |
| Set up local file ingestion | [local-ingest.md](local-ingest.md) |
| Fix "Qdrant unreachable" or "Ollama unreachable" | [recover.md](recover.md) |
| Wire `recall search` into Claude Code / opencode | [mcp-setup.md](mcp-setup.md) |

## Conventions

| Concept | Host | Container |
|---|---|---|
| Qdrant URL | `http://localhost:6333` | `http://qdrant:6333` |
| Ollama URL | `http://localhost:11434` | `http://host.docker.internal:11434` |
| Config file | `~/.config/recall/recall.toml` | `~/.config/recall/recall.container.toml` → mounted at `/config/recall.toml` |
| Secrets | exported env vars or sourced from `~/.config/recall/.env` | `env_file:` in `docker-compose.yml` pointing to `~/.config/recall/.env` |
| Logs | `~/.cache/recall/logs/<name>.log` | `/home/recall/.cache/recall/logs/<name>.log` (named volume `recall_logs`) |

Runbooks assume recall is already installed. For first-time setup see [README.md](../../README.md) and `bootstrap.sh`.

**Quer entender por quê as coisas funcionam assim?** → [../concepts/README.md](../concepts/README.md)
