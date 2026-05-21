# Runbook: Scheduler via Docker

**Quando usar:** primeira vez subindo o stack containerizado, ou após pull de mudanças que alteram `Dockerfile` ou `docker-compose.yml`.

## Pré-requisitos

- Docker daemon rodando (`docker info` sem erro)
- Ollama rodando no host: `curl -s localhost:11434/api/tags | head -c 40`
- `~/.config/recall/recall.container.toml` existe (ver modelo abaixo)
- `~/.config/recall/.env` existe com `GCHAT_WEBHOOK_URL` e `CONFLUENCE_API_TOKEN`

### recall.container.toml mínimo

```toml
[qdrant]
host = "qdrant"
port = 6333

[embedding]
model = "nomic-embed-text"
provider = "ollama"
ollama_host = "http://host.docker.internal:11434"

[[schedules]]
name = "anchor-rfcs"
cron = "0 */3 * * *"
job  = "confluence:page"
page_id = "<your-page-id>"
```

Paths de projetos locais devem usar `/sources/...` (container path), não `~/sources/...`.

## Passos

```bash
docker-compose build recall-scheduler
```
Esperado: `Successfully tagged recall-scheduler:local`

```bash
docker-compose up -d
```
Esperado: `qdrant` sobe, aguarda healthcheck, então `recall-scheduler` inicia.

```bash
docker-compose logs -f recall-scheduler
```
Esperado primeira linha: `recall scheduler starting with N job(s)` seguido de bullets com cada job e `next fire`.

```bash
docker-compose exec recall-scheduler recall scheduler list
```
Esperado: tabela com colunas `NAME`, `JOB`, `CRON`, `NEXT FIRE`.

```bash
docker-compose exec recall-scheduler recall scheduler trigger <schedule-name>
```
Esperado: `✓ N project(s) indexed, M chunks total` (ou similar) + Card no GChat.

### Verificar logs persistidos

```bash
docker-compose exec recall-scheduler cat /home/recall/.cache/recall/logs/<schedule-name>.log
```

## Troubleshooting

- **`Qdrant unreachable at http://qdrant:6333`** → `docker-compose ps qdrant` está healthy? `docker-compose restart qdrant` → aguardar healthcheck.
- **Container sai imediatamente** → `docker-compose logs recall-scheduler` — causa mais comum: `recall.container.toml` não encontrado (path do volume errado) ou TOML inválido.
- **`recall.container.toml` not found** → confirmar que `~/.config/recall/recall.container.toml` existe; o volume monta como `/config/recall.toml` e o scheduler caminha de `/config` para cima.
- **GChat silente após trigger** → `grep GCHAT ~/.config/recall/.env` — URL vazia = silêncio silencioso (não é erro); preencher com webhook válido.
- **Ollama unreachable de dentro do container** → `docker-compose exec recall-scheduler curl -s http://host.docker.internal:11434/api/tags`; se falhar, verificar `extra_hosts: host.docker.internal:host-gateway` no `docker-compose.yml`.
- **Modelo ausente** → `ollama pull nomic-embed-text` no host.

## Relacionado

- [scheduler-host.md](scheduler-host.md) — alternativa sem Docker
- [add-schedule.md](add-schedule.md) — adicionar/editar schedules
- [recover.md](recover.md) — Qdrant/Ollama unreachable
