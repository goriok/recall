# Runbook: Recuperação (Qdrant, Ollama, Collection)

**Quando usar:** scheduler ou ingest reportando "unreachable", embeddings falhando, ou collection com dados corrompidos.

---

## Qdrant unreachable

### No host

`qdrant_guard.py` tenta subir automaticamente via `podman compose up -d`. Se falhar:

```bash
# verificar estado
curl -s localhost:6333/healthz

# subir manualmente (do diretório do repo)
podman compose up -d qdrant
# ou
docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

### No container (`RECALL_IN_CONTAINER=1`)

O bypass desabilita o auto-start. Qdrant deve estar rodando via compose:

```bash
docker-compose ps qdrant
# se não healthy:
docker-compose restart qdrant
# aguardar healthcheck (~30s)
docker-compose logs qdrant
```

Validar de dentro do container:
```bash
docker-compose exec recall-scheduler curl -s http://qdrant:6333/healthz
```
Esperado: `{"title":"qdrant - ..."}`

### Qdrant perdeu dados (volume removido)

```bash
# reindexar tudo
recall ingest --all --recreate
# ou
docker-compose exec recall-scheduler recall ingest --all --recreate
```

---

## Ollama unreachable

### No host

```bash
# verificar se o processo está rodando
curl -s localhost:11434/api/tags

# iniciar se necessário
ollama serve &
```

### No container

O container acessa Ollama via `host.docker.internal:11434`. Testar resolução:

```bash
docker-compose exec recall-scheduler curl -s http://host.docker.internal:11434/api/tags
```

Se falhar: confirmar `extra_hosts: ["host.docker.internal:host-gateway"]` no `docker-compose.yml`.

### Modelo ausente

```bash
ollama list | grep nomic-embed-text
# se não aparecer:
ollama pull nomic-embed-text
```

Modelo padrão: `nomic-embed-text` (768 dims). Configurado em `~/.config/recall/recall.toml` → `[embedding].model`.

---

## Collection corrompida ou com contagem anormal

```bash
recall collections list
```
Mostra nome, dimensão e número de vetores por collection.

Para reindexar uma collection específica (drop + rebuild):
```bash
recall ingest --project <name> --recreate
# ou
docker-compose exec recall-scheduler recall ingest --project <name> --recreate
```

Para apagar manualmente via Qdrant REST:
```bash
curl -X DELETE http://localhost:6333/collections/<collection-name>
```

---

## Troubleshooting rápido

| Sintoma | Causa provável | Fix |
|---|---|---|
| `Connection refused` no port 6333 | Qdrant não está rodando | `podman compose up -d qdrant` |
| `Connection refused` no port 11434 | Ollama não está rodando | `ollama serve` |
| `model 'nomic-embed-text' not found` | Modelo não baixado | `ollama pull nomic-embed-text` |
| `Qdrant unreachable` em container | Container bypass ativo; Qdrant não healthcheck | `docker-compose restart qdrant` |
| `host.docker.internal: no such host` | `extra_hosts` ausente no compose | Verificar `docker-compose.yml` |
| Chunks duplicados após reingest | Normal — IDs são SHA-256 determinísticos; upsert é idempotente | Nenhum |

## Relacionado

- [scheduler-docker.md](scheduler-docker.md) — stack Docker
- [scheduler-host.md](scheduler-host.md) — auto-start Qdrant no host
