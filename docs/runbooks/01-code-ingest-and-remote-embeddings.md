# Runbook 01 — Operar o ingest: embeddings remotos, repositórios de código e Qdrant servidor

Operação do dia a dia depois da instalação; a instalação e o primeiro índice estão no [runbook 02](02-install-plugin-and-first-index.md).

```
+------------------------------+
| 1. Embeddings remotos        |
+------------------------------+
               |
               v
+------------------------------+
| 2. Registrar uma fonte       |
+------------------------------+
               |
               v
+------------------------------+
| 3. Ingerir                   |
+------------------------------+
               |
               v
+------------------------------+
| 4. Buscar                    |
+------------------------------+
               |
               v
+------------------------------+
| 5. Qdrant servidor (opcional)|
+------------------------------+
               |
               v
+------------------------------+
| 6. Testes                    |
+------------------------------+
```

## 1. Embeddings remotos

A configuração básica (`RECALL_EMBEDDING_BASE_URL`, `RECALL_EMBEDDING_MODEL`, `RECALL_EMBEDDING_API_KEY` em `~/.config/recall/.env`) está no [runbook 02](02-install-plugin-and-first-index.md#3-configurar-embeddings). Aqui ficam as variáveis opcionais e as regras de confiança.

```bash
RECALL_EMBEDDING_PROVIDER=openai
RECALL_EMBEDDING_API_KEY_ENV=MINHA_VARIAVEL
RECALL_EMBEDDING_BATCH_SIZE=16
RECALL_TRUSTED_HOSTS=outro-host.example.com,qdrant.interno.example.com
```

`RECALL_EMBEDDING_API_KEY_ENV` indica outra variável que guarda a chave, `RECALL_EMBEDDING_BATCH_SIZE` aceita no máximo 32 e `RECALL_TRUSTED_HOSTS` é uma lista separada por vírgula.

Um `recall.toml` de projeto só pode usar um endereço remoto que o `.env` global (`RECALL_EMBEDDING_BASE_URL`), o `recall.toml` global, `[security] trusted_hosts` ou `RECALL_TRUSTED_HOSTS` já declarem, e só pode usar com ele a variável de chave que o arquivo global associa àquele host; hosts remotos exigem https.

Para conteúdo pessoal, sobrescreva o provedor por fonte:

```toml
[[sources]]
root = "~/sources/goriok/ctx-langs/topics"
[sources.embedding]
provider = "ollama"
model = "nomic-embed-text"
```

## 2. Registrar uma fonte

Código usa `[[repos]]` e vira a coleção `code.<name>`:

```toml
[[repos]]
name = "my-backend"
root = "~/sources/acme/my-backend"
globs = ["**/*.py", "**/*.go", "**/*.ts", "**/*.md"]
[repos.graphify]
enabled = true
```

Documentação em Markdown usa `[[sources]]`, com uma coleção por subpasta de `topics/`:

```toml
[[sources]]
root = "~/sources/acme/ctx-docs/topics"
```

Python vira chunks por função, método e classe; Go, JavaScript e Rust viram chunks por símbolo (precisam do extra `code`, passo 1 do runbook 02); as demais extensões viram janelas de 60 linhas com overlap de 10. O Graphify é opcional (`uv tool install graphifyy`), e sem ele o ingest segue sem comunidade, god node e símbolos relacionados.

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
| `refusing to talk to untrusted host` | `recall.toml` local aponta para um host que o global não declara | declarar o host no `.env` global, no `recall.toml` global, em `[security] trusted_hosts` ou em `RECALL_TRUSTED_HOSTS` |
| `$VAR is not authorized for` | o `recall.toml` local pede, para um host confiável, outra variável de chave que a do arquivo global | usar a variável que o arquivo global associa ao host |
| `not pruning: some projects failed` | `--prune` não roda quando um projeto falhou na mesma execução | corrigir o erro listado e repetir |
| `was indexed with ... re-run 'recall ingest --recreate'` | coleção criada com outro modelo | `recall ingest <projeto> --recreate` |
| `another process (recall-mcp?) has the embedded Qdrant store open` | lock exclusivo do store embutido | fechar o outro processo ou usar Qdrant servidor |
| `graph metadata unavailable` | `graphify` ausente, timeout ou erro | instalar o Graphify; o ingest continua sem grafo |
| `no files under ... match` | glob não casa nenhum arquivo | revisar `globs`/`glob` e `path_exclude` |
| `tree-sitter support for go is not installed` | gramáticas opcionais ausentes | reinstalar o CLI com `recall[code]` (runbook 02, passo 1); os arquivos foram indexados como janelas de linhas |
