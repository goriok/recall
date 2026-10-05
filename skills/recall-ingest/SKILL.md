---
name: recall-ingest
description: Configura e roda a indexação do recall (recall.toml, recall ingest) para documentação e repositórios de código, e diagnostica quando a busca vem vazia ou o ingest falha. Use quando o usuário pedir para indexar um repo, adicionar uma fonte ao recall, reindexar após mudanças ou quando o recall não encontrar nada.
---

# Indexar com o recall

O índice só existe depois de `recall ingest`, e ele é idempotente: reingerir troca os chunks dos arquivos alterados e remove os dos arquivos apagados. A busca (`search_docs`, `search_code`) nunca indexa nada sozinha.

## Peça confirmação antes de

- Editar o `~/.config/recall/recall.toml` global.
- `recall ingest --recreate` (apaga e refaz a coleção) e `recall ingest --all --prune` (apaga coleções de tópicos que sumiram).
- Trocar o provedor de embeddings de uma coleção que já existe (exige `--recreate`).

Rodar `recall ingest <nome>` numa fonte nova ou `recall ingest --all` sem `--recreate` é seguro e repetível. Nunca imprima nem grave valores de chaves de API: o `recall.toml` guarda só o nome da variável (`api_key_env`).

## Passo a passo

1. Veja o que já existe: `list_sources` (MCP) ou `recall collections list`.
2. Adicione a fonte ao `recall.toml` (o mais próximo do projeto, ou o global se o usuário preferir):

```toml
# documentação: uma coleção por subpasta de topics/
[[sources]]
root = "~/sources/acme/ctx-docs/topics"

# código: uma coleção code.<name> por repositório
[[repos]]
name = "my-backend"
root = "~/sources/acme/my-backend"
globs = ["**/*.py", "**/*.go", "**/*.js", "**/*.rs", "**/*.md"]
```

3. Rode `recall ingest my-backend` (ou `--all`). O resumo mostra arquivos removidos, arquivos pulados e avisos.
4. Confira com `list_sources` e faça uma busca de teste com uma frase que você sabe que está no conteúdo.

## Embeddings

- Padrão: Ollama local (`nomic-embed-text`, precisa de `ollama pull nomic-embed-text`). Corta cada chunk em 1500 caracteres.
- Endpoint remoto compatível com OpenAI (rápido e sem o corte de 1500 caracteres). Configure no arquivo global `~/.config/recall/.env`, que o `recall` lê (só variáveis `RECALL_*`; nunca um `.env` do diretório atual), em vez de colocar o endereço num repositório:

```bash
# ~/.config/recall/.env
RECALL_EMBEDDING_BASE_URL=https://embeddings.example.com/v1
RECALL_EMBEDDING_MODEL=nomic-embed-text-v1-5
RECALL_EMBEDDING_API_KEY=<API_KEY>
```

- Conteúdo pessoal fica no Ollama: sobrescreva por fonte com `[sources.embedding]` ou `[repos.embedding]` e `provider = "ollama"`.
- Uma coleção fica presa ao modelo que a criou; vetores de modelos diferentes não são comparáveis.

## Linguagens e Graphify

- Python, Go, JavaScript e Rust viram chunks por símbolo (Go, JS e Rust precisam do extra: `uv tool install --from '.[code]' recall`); as demais viram janelas de linhas. Liste as extensões em `globs`: o padrão é só `**/*.py` e `**/*.md`.
- O Graphify (`graphify` no PATH) é opcional e acrescenta comunidade, god node e símbolos relacionados. Sem ele o ingest continua com um aviso.
- `target/`, `vendor/`, `node_modules/`, `.venv/` e `graphify-out/` são excluídos por padrão; arquivos do `.gitignore`, segredos (`.env`, `*.pem`, `*credentials*`), binários e arquivos acima de 512 KB não entram.

## Diagnóstico

| Sintoma | Causa | Ação |
|---|---|---|
| `No results found.` | fonte não indexada, nome errado ou `--in` com coleção inexistente | `list_sources`; rodar `recall ingest <nome>` |
| `no files under ... match` | `globs` não casam nada | revisar `globs` e `path_exclude` |
| `was indexed with ... re-run 'recall ingest --recreate'` | provedor de embeddings mudou | confirmar com o usuário e rodar `--recreate` |
| `the selected collections use different embedding models` | busca ampla misturando modelos | restringir com `project` ou `repo` |
| `refusing to send $VAR to untrusted host` | `recall.toml` local aponta para um host que o global não declara | pôr o endpoint em `RECALL_EMBEDDING_BASE_URL` no `.env` global, ou declarar o host no `recall.toml` global, em `[security] trusted_hosts`, ou em `RECALL_TRUSTED_HOSTS` |
| `environment variable RECALL_EMBEDDING_API_KEY is not set` | chave ausente | `RECALL_EMBEDDING_API_KEY=<API_KEY>` em `~/.config/recall/.env` (vale para Claude Code, Hermes e agy) |
| `embedding endpoint returned HTTP 400` | `batch_size` acima de 32 ou modelo inválido | usar `batch_size <= 32` |
| `another process (recall-mcp?) has the embedded Qdrant store open` | o store embutido só abre em um processo por vez | fechar o outro processo, ou usar Qdrant servidor |
| `graph metadata unavailable` | `graphify` ausente, timeout ou erro | instalar o Graphify; o ingest segue sem grafo |
| `tree-sitter support for go is not installed` | extra `code` ausente | `uv tool install --from '.[code]' recall` |
