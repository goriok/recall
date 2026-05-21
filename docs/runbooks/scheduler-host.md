# Runbook: Scheduler no Host

**Quando usar:** rodar o daemon diretamente no host, sem Docker — útil em dev ou máquinas sem daemon Docker.

## Pré-requisitos

- `uv` instalado (`uv --version`)
- Ollama rodando: `curl -s localhost:11434/api/tags`
- Qdrant rodando: `curl -s localhost:6333/healthz` (ou `podman compose up -d` no repo)
- `~/.config/recall/recall.toml` com pelo menos um `[[schedules]]`
- Secrets em `~/.config/recall/.env` ou exportados no shell

## Passos

### Instalar / atualizar o binário

```bash
# do diretório raiz do repo recall
uv tool install --reinstall --from . recall
```
Esperado: `Installed 2 executables: recall, recall-mcp`

### Carregar secrets

```bash
set -a && source ~/.config/recall/.env && set +a
```

### Verificar schedules configurados

```bash
recall scheduler list
```
Esperado: tabela com `NAME`, `JOB`, `CRON`, `NEXT FIRE`. Se aparecer "No schedules configured" ver troubleshooting abaixo.

### Trigger manual (smoke test)

```bash
recall scheduler trigger anchor-rfcs
```
Esperado: `✓ <resultado>` no terminal + Card no GChat. Log gerado em `~/.cache/recall/logs/anchor-rfcs.log`.

### Rodar daemon em foreground

```bash
recall scheduler run
```
Daemon bloqueia. Parar com `Ctrl-C` (SIGINT) ou `kill -TERM <pid>`.

### Rodar daemon em background (nohup)

```bash
nohup recall scheduler run >> ~/.cache/recall/logs/scheduler.log 2>&1 &
echo $! > ~/.cache/recall/scheduler.pid
```
Para parar:
```bash
kill $(cat ~/.cache/recall/scheduler.pid)
```

## Troubleshooting

- **"No schedules configured"** → `find_config()` achou um `recall.toml` sem `[[schedules]]` no CWD ou acima. Rodar de `~` ou de um dir sem `recall.toml` local para alcançar `~/.config/recall/recall.toml`.
- **Daemon termina em < 2s sem output** → ver `~/.cache/recall/logs/<schedule>.log`; causa comum: ConfigError no primeiro job.
- **`recall: command not found` após install** → `uv tool bin` está no PATH? `export PATH="$(uv tool bin):$PATH"`.
- **Pega versão antiga após `--reinstall`** → `uv tool list | grep recall` — se versão errada: `uv tool uninstall recall && uv tool install --from . recall`.
- **Qdrant auto-start falha** → `qdrant_guard.py` tenta `podman compose up -d`; se Podman ausente, subir Qdrant manualmente (`docker run -p 6333:6333 qdrant/qdrant`).

## Relacionado

- [scheduler-docker.md](scheduler-docker.md) — alternativa containerizada
- [add-schedule.md](add-schedule.md) — adicionar/editar schedules
- [recover.md](recover.md) — Qdrant/Ollama unreachable
