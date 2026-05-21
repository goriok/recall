# Runbook: Adicionar ou Editar um Schedule

**Quando usar:** adicionar novo `[[schedules]]`, editar cron/params, ou remover uma entry.

## Pré-requisitos

- Config file editável: `~/.config/recall/recall.toml` (host) ou `~/.config/recall/recall.container.toml` (Docker)
- Scheduler rodando (para reload)

## Sintaxe por job type

| Job | Required params | Optional params |
|---|---|---|
| `confluence:page` | `page_id` | `collection`, `recreate` |
| `confluence:folder` | `folder_id` | `collection`, `recreate` |
| `confluence:space` | `space` | `collection`, `recreate` |
| `confluence:label` | `label` | `collection`, `recreate` |
| `local:all` | — | `only`, `skip`, `recreate` |
| `local:project` | `project` | `recreate` |
| `local:source` | `source` | `recreate` |

Validação vive em `src/recall/scheduler/config.py:6-25`.

### Exemplos mínimos

```toml
# Confluence page tree (a cada 3h)
[[schedules]]
name    = "my-rfcs"
cron    = "0 */3 * * *"
job     = "confluence:page"
page_id = "123456789"

# Todos os projetos locais (a cada 3h, offset de 30min)
[[schedules]]
name = "local-all"
cron = "30 */3 * * *"
job  = "local:all"
skip = ["trivia"]         # excluir parent dirs que causariam duplicatas

# Projeto local específico (a cada hora)
[[schedules]]
name    = "docs-hourly"
cron    = "0 * * * *"
job     = "local:project"
project = "my-project"   # deve bater com [[projects]].name em recall.toml
```

Sintaxe cron: `minuto hora dia mês dia-semana`. Validador online: [crontab.guru](https://crontab.guru).

## Passos

### 1. Editar o config

```bash
$EDITOR ~/.config/recall/recall.toml          # host
$EDITOR ~/.config/recall/recall.container.toml # Docker
```

### 2. Recarregar o scheduler

**Host** — o daemon não observa mudanças em disco; reiniciar é obrigatório:
```bash
kill $(cat ~/.cache/recall/scheduler.pid)
recall scheduler run &
```

**Docker:**
```bash
docker-compose restart recall-scheduler
```

### 3. Verificar

```bash
# host
recall scheduler list

# Docker
docker-compose exec recall-scheduler recall scheduler list
```
Esperado: nova entry aparece na tabela com `NEXT FIRE` calculado.

### 4. Smoke test

```bash
recall scheduler trigger <new-name>
# ou
docker-compose exec recall-scheduler recall scheduler trigger <new-name>
```
Esperado: resultado no terminal + Card no GChat (se `GCHAT_WEBHOOK_URL` configurado).

## Troubleshooting

- **`unknown job type 'X'`** → typo em `job =`; lista válida: `confluence:{page,folder,space,label}`, `local:{all,project,source}`.
- **`missing required param 'Y'`** → ver tabela acima; cada job tem seus required params.
- **`unknown project 'X'`** (em `local:project`) → nome deve bater com `[[projects]].name` ou com nome de subdir auto-discovered. `recall ingest --all` lista os projetos encontrados.
- **Nova entry não aparece em `list`** → daemon não recarregou; reiniciar obrigatório.
- **Cron não dispara no horário esperado** → validar expressão em [crontab.guru](https://crontab.guru); `recall scheduler list` mostra o próximo fire calculado por `croniter`.

## Relacionado

- [confluence-ingest.md](confluence-ingest.md) — detalhes de auth Confluence
- [local-ingest.md](local-ingest.md) — configurar projetos e sources locais
