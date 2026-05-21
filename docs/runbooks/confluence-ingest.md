# Runbook: Ingestão Confluence

**Quando usar:** configurar Confluence pela primeira vez, rotacionar token, ou debugar erros 401/404.

## Pré-requisitos

- API token gerado em: `https://id.atlassian.com/manage-profile/security/api-tokens`
- URL e email da conta Confluence Cloud (ou URL do servidor para Server/DC)

## Passos

### 1. Configurar credenciais

Adicionar ao `~/.config/recall/.env`:
```
CONFLUENCE_API_TOKEN=<seu-token>
```

Confirmar que `[confluence]` no `recall.toml` (ou `recall.container.toml`) está correto:

```toml
[confluence]
url       = "https://yourorg.atlassian.net"  # Cloud
auth_type = "token"
email     = "you@yourorg.com"                # Cloud — obrigatório
token     = "{env:CONFLUENCE_API_TOKEN}"     # lê de CONFLUENCE_API_TOKEN no env
```

Para Confluence Server/DC: omitir `email`; auth via Bearer token. Detecção automática: `"atlassian.net" in url` → Cloud (`src/recall/confluence/config.py:38-45`).

### 2. Smoke test ad-hoc

```bash
# host
set -a && source ~/.config/recall/.env && set +a
recall ingest-confluence --page-id <id>

# Docker
docker-compose exec recall-scheduler recall ingest-confluence --page-id <id>
```
Esperado: `✓ N pages indexed, M chunks total`

Encontrar o ID de uma página: abrir a página no browser → URL contém `/pages/<id>/` ou `pageId=<id>`.

### 3. Adicionar como schedule recorrente

```toml
[[schedules]]
name    = "my-docs"
cron    = "0 */3 * * *"
job     = "confluence:page"
page_id = "<id>"
```

Para pasta (folder):
```toml
[[schedules]]
name      = "my-folder"
cron      = "15 */3 * * *"
job       = "confluence:folder"
folder_id = "<id>"
```

Ver [add-schedule.md](add-schedule.md) para reload e validação.

## Troubleshooting

- **401 Unauthorized** → token expirado ou sem permissão na página; gerar novo token em `id.atlassian.com/manage-profile/security/api-tokens` e atualizar `~/.config/recall/.env`.
- **404 em `confluence:folder`** → confirmar que é um folder Cloud; a ingestão usa o endpoint v1 `content/{id}/child/page` (`src/recall/confluence/client.py` — `get_folder_children` delega para `get_children`).
- **Nenhuma página retornada** → ID correto mas sem permissão; verificar permissões do token na Space Settings.
- **Páginas com conteúdo vazio após ingest** → conteúdo pode ser Confluence macro (gráficos, draw.io) não exportável como HTML; comportamento esperado.
- **Lento (~1-2s/página)** → normal — cada página faz chamada REST + HTML→Markdown + embed Ollama.
- **`{env:CONFLUENCE_API_TOKEN}` não resolvido** → token não está no ambiente; `echo $CONFLUENCE_API_TOKEN` deve retornar o valor.

## Relacionado

- [add-schedule.md](add-schedule.md) — wiring no scheduler
- [recover.md](recover.md) — Qdrant/Ollama unreachable durante ingest
