# Runbook 01 — Instalar o plugin e fazer o primeiro índice

Do zero até uma busca funcionando no Claude Code, Hermes ou Antigravity (`agy`).

```
+----------------------------+
| 1. Instalar o CLI          |
+----------------------------+
              |
              v
+----------------------------+
| 2. Instalar o plugin       |
+----------------------------+
              |
              v
+----------------------------+
| 3. Configurar embeddings   |
+----------------------------+
              |
              v
+----------------------------+
| 4. Registrar a fonte       |
+----------------------------+
              |
              v
+----------------------------+
| 5. Indexar                 |
+----------------------------+
              |
              v
+----------------------------+
| 6. Verificar               |
+----------------------------+
```

## 1. Instalar o CLI

```bash
uv tool install --from "recall[code] @ git+https://github.com/goriok/recall.git" recall
```

Instala `recall` e `recall-mcp`, e o extra `code` traz as gramáticas de Go, JavaScript e Rust; sem ele esses arquivos viram janelas de linhas, e Python e Markdown não dependem dele.

## 2. Instalar o plugin

Claude Code:

```
/plugin marketplace add goriok/recall
/plugin install recall@recall
/reload-plugins
```

Hermes:

```bash
hermes plugins install goriok/recall
hermes plugins enable recall
```

Antigravity:

```bash
git clone git@github.com:goriok/recall.git
agy plugin install ./recall/plugins/recall
```

Cada host recebe o servidor MCP `recall-mcp` (via `uvx`) e as skills `recall-search`, `recall-code` e `recall-ingest`; o Hermes instala pacotes portáteis desabilitados, por isso o `enable`.

## 3. Configurar embeddings

Com Ollama local, basta baixar o modelo:

```bash
ollama pull nomic-embed-text
```

Com um endpoint remoto compatível com OpenAI, grave o endereço e a chave no arquivo global, nunca dentro de um repositório:

```bash
mkdir -p ~/.config/recall && touch ~/.config/recall/.env && chmod 600 ~/.config/recall/.env
cat >> ~/.config/recall/.env <<'EOF'
RECALL_EMBEDDING_BASE_URL=https://embeddings.example.com/v1
RECALL_EMBEDDING_MODEL=nomic-embed-text-v1-5
RECALL_EMBEDDING_API_KEY=<API_KEY>
EOF
```

O `>>` acrescenta sem apagar o que já existe no arquivo, e o `recall` lê dele só as variáveis `RECALL_*`, em qualquer host, inclusive o Hermes, que filtra o ambiente do servidor MCP.

## 4. Registrar a fonte

```bash
cat >> ~/.config/recall/recall.toml <<'EOF'
[[repos]]
name = "my-backend"
root = "~/sources/acme/my-backend"
globs = ["**/*.py", "**/*.go", "**/*.js", "**/*.rs", "**/*.md"]
EOF
```

Cada `[[repos]]` vira a coleção `code.<name>`; documentação em tópicos usa `[[sources]]`, descrito no [runbook 02](02-operate-ingest.md#1-registrar-uma-fonte).

## 5. Indexar

```bash
recall ingest my-backend
```

O resumo mostra os chunks indexados, os arquivos pulados e os avisos, e repetir o comando é seguro: ele troca só o que mudou e remove o que foi apagado.

## 6. Verificar

```bash
recall collections list
recall search "como o retry funciona" --in code.my-backend --top 3
```

A busca devolve `file_path:linhas` e o símbolo de cada resultado; confirme no host que o servidor MCP está ativo e chame a ferramenta `list_sources`.

```bash
claude mcp list
hermes mcp list
```

## Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `recall: command not found` | o diretório de executáveis do `uv` não está no `PATH` | `uv tool update-shell` e abrir um novo terminal |
| `/plugin install recall@recall` não encontra o plugin | o marketplace não foi adicionado | repetir `/plugin marketplace add goriok/recall` |
| o plugin instalado não tem `search_code` nem `list_sources` | versão antiga em cache | Claude Code: `/plugin marketplace update goriok/recall` e `/reload-plugins`; Hermes: `hermes plugins update recall`; agy: `git pull` e instalar de novo |
| no Hermes as skills não aparecem | pacote portátil instalado desabilitado | `hermes plugins enable recall` |
| `environment variable RECALL_EMBEDDING_API_KEY is not set` | chave ausente | conferir a linha no `~/.config/recall/.env` |
| `refusing to talk to untrusted host` | `recall.toml` local aponta para um host que o global não declara | colocar o endereço em `RECALL_EMBEDDING_BASE_URL` no `.env` global ou em `RECALL_TRUSTED_HOSTS` |
| `tree-sitter support for go is not installed` | CLI instalado sem o extra `code` | repetir o passo 1 com `recall[code]` |
| `another process (recall-mcp?) has the embedded Qdrant store open` | o store embutido abre em um processo por vez | fechar o outro processo ou usar Qdrant servidor ([runbook 04](04-qdrant-server.md)) |
| `No results found.` | fonte ainda não indexada ou `--in` com nome errado | `recall collections list` e repetir o passo 5 |

Os demais erros estão nas tabelas dos runbooks [02 (ingest)](02-operate-ingest.md#troubleshooting), [03 (embeddings remotos)](03-remote-embeddings.md#troubleshooting) e [04 (Qdrant servidor)](04-qdrant-server.md#troubleshooting).
