# Runbook 01 — Ingest de código, embeddings remotos e Qdrant servidor

## 1. Configurar os embeddings remotos

Mantenha o endpoint e a chave fora de qualquer repositório, no arquivo global `~/.config/recall/.env`. O `recall` lê desse arquivo só as variáveis `RECALL_*` (nunca as demais, nunca um `.env` do diretório atual), inclusive quando roda dentro do `recall-mcp` de qualquer host:

```bash
# ~/.config/recall/.env
RECALL_EMBEDDING_BASE_URL=https://embeddings.example.com/v1
RECALL_EMBEDDING_MODEL=nomic-embed-text-v1-5
RECALL_EMBEDDING_API_KEY=<API_KEY>
```

Com isso o `recall.toml` não precisa de tabela `[embedding]`. Opcionais: `RECALL_EMBEDDING_PROVIDER`, `RECALL_EMBEDDING_API_KEY_ENV` (nome de outra variável que guarda a chave) e `RECALL_EMBEDDING_BATCH_SIZE`. O host de `RECALL_EMBEDDING_BASE_URL` passa a ser confiável para qualquer `recall.toml` local; um host diferente precisa estar no `recall.toml` global, em `[security] trusted_hosts` ou em `RECALL_TRUSTED_HOSTS` (lista separada por vírgula), e hosts remotos exigem https.

O lote do endpoint é no máximo 32 (`batch_size` acima disso é rejeitado). Para conteúdo pessoal, sobrescreva por fonte:

```toml
[[sources]]
root = "~/sources/goriok/ctx-langs/topics"
[sources.embedding]
provider = "ollama"
model = "nomic-embed-text"
```

## 2. Registrar um repositório de código

```toml
[[repos]]
name = "my-backend"
root = "~/sources/acme/my-backend"
globs = ["**/*.py", "**/*.go", "**/*.ts", "**/*.md"]
[repos.graphify]
enabled = true
```

Python vira chunks por função/método/classe; Go, JavaScript e Rust viram chunks por símbolo (precisam das gramáticas opcionais: `uv tool install --from '.[code]' recall`); as demais extensões viram janelas de 60 linhas com overlap de 10. Graphify é opcional (`uv tool install graphifyy`); sem ele o ingest segue sem comunidade, god node e símbolos relacionados.

## 3. Ingerir

```bash
recall ingest my-backend
recall ingest --all
recall ingest --all --prune      # remove coleções de tópicos que sumiram: pede confirmação (--yes pula) e não roda se algum projeto falhou ou se o diretório da fonte não existe
recall ingest my-backend --recreate   # obrigatório ao trocar de provedor de embeddings
```

O resumo mostra arquivos removidos do índice, arquivos pulados (`too_large`, `binary`, `denylist`, `outside_root`, `unreadable`) e avisos.

## 4. Buscar

Antes de buscar, a tool MCP `list_sources` mostra o que está indexado, o modelo de cada coleção e a data do último ingest.

```bash
recall search "retry with backoff" --in code.my-backend --top 5
```

No Claude Code / opencode, as tools `search_code`, `search_docs` e `explain_architecture` do `recall-mcp` devolvem `repo`, `file_path`, intervalo de linhas, `symbol`, `community`, `god_node` e `related`. Resolva `file_path` contra o checkout do repo antes de ler ou editar.

## 5. Qdrant servidor (opcional)

```toml
[qdrant]
host = "qdrant.internal"
port = 6333
prefer_grpc = true
grpc_port = 6334
https = false
api_key_env = "QDRANT_API_KEY"
```

O Podman só é iniciado automaticamente para `localhost` em http. Para um servidor local de teste:

```bash
podman run -d --rm --name recall-it-qdrant -p 16333:6333 -p 16334:6334 docker.io/qdrant/qdrant:latest
RECALL_TEST_QDRANT_URL=http://localhost:16333 uv run python -m pytest -m integration
RECALL_TEST_QDRANT_URL=http://localhost:16333 RECALL_TEST_QDRANT_GRPC_PORT=16334 uv run python -m pytest -m integration
podman stop recall-it-qdrant
```

## 6. Testes

```bash
uv sync --group dev
uv run python -m pytest --cov                 # unitários (integration e remote desligados por padrão)
RECALL_TEST_EMBEDDING_URL="https://embeddings.example.com/v1" RECALL_EMBEDDING_API_KEY="<API_KEY>" uv run python -m pytest -m remote
```

## Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `embedding endpoint returned HTTP 400` | `batch_size` acima de 32 ou modelo inválido | usar `batch_size <= 32` |
| `HTTP 404 model_not_found` | nome do modelo errado | `model = "nomic-embed-text-v1-5"` |
| `environment variable RECALL_EMBEDDING_API_KEY is not set` | chave ausente | colocar `RECALL_EMBEDDING_API_KEY=<API_KEY>` em `~/.config/recall/.env` (vale para todos os hosts, inclusive o Hermes, que filtra o ambiente do servidor MCP) |
| `refusing to send $VAR to untrusted host` | `recall.toml` local aponta para um host não declarado no global | declarar o host no `recall.toml` global, em `[security] trusted_hosts`, ou exportar `RECALL_TRUSTED_HOSTS` |
| `was indexed with ... re-run 'recall ingest --recreate'` | coleção criada com outro modelo | `recall ingest <projeto> --recreate` |
| `another process (recall-mcp?) has the embedded Qdrant store open` | lock exclusivo do store embutido | fechar o outro processo ou usar Qdrant servidor |
| `graph metadata unavailable` | `graphify` ausente, timeout ou erro | instalar o Graphify; o ingest continua sem grafo |
| `no files under ... match` | glob não casa nenhum arquivo | revisar `globs`/`glob` e `path_exclude` |
| `tree-sitter support for go is not installed` | gramáticas opcionais ausentes | `uv tool install --from '.[code]' recall` (os arquivos foram indexados como janelas de linhas) |
