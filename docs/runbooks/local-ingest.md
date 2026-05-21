# Runbook: Ingestão Local

**Quando usar:** configurar projetos e diretórios locais para indexação, ou ajustar filtros `only`/`skip`.

## Pré-requisitos

- Paths dos projetos existem no disco
- Ollama e Qdrant rodando (ver [recover.md](recover.md) se não)

## Dois modos de configuração

### Explícito (`[[projects]]`)

Path, collection e glob customizados por projeto:

```toml
[[projects]]
name       = "my-project"
path       = "~/sources/my-project/docs"  # container: "/sources/my-project/docs"
collection = "my-project"
glob       = "**/*.md"
```

### Auto-discover (`[[sources]]`)

Todo subdiretório com arquivos matching `glob` vira uma collection:

```toml
[[sources]]
root = "~/sources"          # container: "/sources"
glob = "**/*.md"
exclude = [
  "node_modules", ".venv", "dist", "__pycache__", ".git",
  "recall",                 # evitar auto-indexar o próprio projeto
  "bkp", "obsidian",        # dirs não-código
]
```

Projetos explícitos têm precedência: se `[[projects]]` define `name = "hyle"`, o subdir `hyle` não é auto-discovered novamente (`src/recall/config.py:83-112`).

## Passos

### Smoke test manual

```bash
# indexar projeto explícito
recall ingest --project my-project

# indexar tudo (explícitos + auto-discovered)
recall ingest --all

# Docker
docker-compose exec recall-scheduler recall ingest --all
```
Esperado: `✓ N project(s) indexed, M chunks total`

### Verificar o que seria indexado

```bash
recall ingest --all --dry-run
```
*(ainda não existe — listar projetos hoje exige `recall ingest --all` com Qdrant up e observar o output)*

### Adicionar como schedule

```toml
# Todos (a cada 3h)
[[schedules]]
name = "local-all"
cron = "30 */3 * * *"
job  = "local:all"
skip = ["trivia"]      # excluir parent dir que shadow-indexaria sub-projetos

# Projeto específico (a cada hora)
[[schedules]]
name    = "hyle-hourly"
cron    = "0 * * * *"
job     = "local:project"
project = "hyle"

# Um [[sources]] root inteiro
[[schedules]]
name   = "analysis-daily"
cron   = "0 3 * * *"
job    = "local:source"
source = "~/sources"   # container: "/sources"
```

### Filtros `only` e `skip` em `local:all`

```toml
[[schedules]]
name = "local-subset"
cron = "0 */6 * * *"
job  = "local:all"
only = ["hyle", "mcx-companion"]   # só estes dois (allowlist)
# skip = [...]                     # ignorado quando 'only' está presente
```

`only` precede `skip` — se ambos presentes, `skip` é ignorado (`src/recall/commands/ingest.py:22-26`).

## Troubleshooting

- **`unknown project 'X'`** (em `local:project`) → `X` não bate com `[[projects]].name` nem com subdir auto-discovered. `recall ingest --all` imprime todos os projetos encontrados.
- **Mesmo conteúdo indexado 2×** → parent dir em `[[sources]]` auto-discovers sub-projetos já cobertos por `[[projects]]`. Adicionar o parent em `skip` do schedule ou em `exclude` do source. Exemplo: `trivia` é pai de `hyle`; adicionar `skip = ["trivia"]` no schedule ou `"trivia"` em `exclude`.
- **Container não acha `/sources/X`** → paths em `recall.container.toml` devem ser `/sources/...` (container path), não `~/sources/...`. Confirmar que `${HOME}/sources` está montado em `/sources:ro` no `docker-compose.yml`.
- **Collection vazia após ingest** → nenhum arquivo bate o `glob`; verificar `glob = "**/*.md"` e que o path existe e tem `.md` files.
- **`--recreate` acidentalmente** → apaga e re-cria a collection; seguro (IDs determinísticos), mas lento em collections grandes.

## Relacionado

- [add-schedule.md](add-schedule.md) — wiring no scheduler
- [scheduler-docker.md](scheduler-docker.md) — mounts de volume para container
- [recover.md](recover.md) — collection corrompida
