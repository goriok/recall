# Runbook 02 — Operar o ingest

Registrar fontes, indexar, reindexar, limpar e buscar; a instalação está no [runbook 01](01-install-plugin-and-first-index.md), os embeddings remotos no [03](03-remote-embeddings.md) e o Qdrant servidor no [04](04-qdrant-server.md).

```
+------------------------------+
| 1. Registrar uma fonte       |
+------------------------------+
               |
               v
+------------------------------+
| 2. Ingerir                   |
+------------------------------+
               |
               v
+------------------------------+
| 3. Reindexar                 |
+------------------------------+
               |
               v
+------------------------------+
| 4. Limpar tópicos removidos  |
+------------------------------+
               |
               v
+------------------------------+
| 5. Buscar                    |
+------------------------------+
```

## 1. Registrar uma fonte

Código usa `[[repos]]` e vira a coleção `code.<name>`:

```toml
[[repos]]
name = "my-backend"
root = "~/sources/acme/my-backend"
globs = ["**/*.py", "**/*.go", "**/*.ts", "**/*.md"]
[repos.graphify]
enabled = true
```

Repos de IaC (YAML de Helm/ArgoCD) usam o chunker por chave e `path_labels`, que prefixam o caminho como `env=… region=…` no embedding; o primeiro template que casa vale:

```toml
[[repos]]
name = "iac"
root = "~/sources/acme/iac"
globs = ["**/Chart.yaml", "**/values.yaml"]
path_exclude = [".git", "templates"]
path_labels = [
  "{env}/{region}/dc/{dc}/override/{product}/{chart}/*",
  "{env}/{region}/service/{product}/{chart}/*",
]
```

Documentação em Markdown usa `[[sources]]`, com uma coleção por subpasta de `topics/`:

```toml
[[sources]]
root = "~/sources/acme/ctx-docs/topics"
```

Python vira chunks por função, método e classe; Go, JavaScript e Rust viram chunks por símbolo (precisam do extra `code`, passo 1 do runbook 01); as demais extensões viram janelas de 60 linhas com overlap de 10. O Graphify é opcional (`uv tool install graphifyy`), e sem ele o ingest segue sem comunidade, god node e símbolos relacionados.

## 2. Ingerir

```bash
recall ingest my-backend
recall ingest --all
```

O resumo mostra os chunks indexados, os arquivos removidos do índice, os pulados (`too_large`, `binary`, `denylist`, `outside_root`, `unreadable`) e os avisos.

## 3. Reindexar

```bash
recall ingest my-backend
recall ingest my-backend --recreate
```

Repetir o comando é seguro e troca só o que mudou; `--recreate` apaga e refaz a coleção, e é obrigatório quando o provedor de embeddings muda ([runbook 03](03-remote-embeddings.md#4-trocar-o-provedor-de-uma-coleção)).

## 4. Limpar tópicos removidos

```bash
recall ingest --all --prune
```

Remove as coleções de tópicos que sumiram da fonte, depois de pedir confirmação (`--yes` pula); ele ignora fontes cujo diretório não existe, nunca toca `recall-meta` nem `code.*` e não roda se algum projeto falhou na mesma execução.

## 5. Buscar

```bash
recall search "retry with backoff" --in code.my-backend --top 5
```

No host, `search_code`, `search_docs` e `explain_architecture` devolvem `file_path`, intervalo de linhas e símbolo, e `list_sources` mostra o que está indexado, o modelo de cada coleção e a data do último ingest; resolva `file_path` contra o checkout do repo antes de ler ou editar.

## Troubleshooting

| Sintoma | Causa | Ação |
|---|---|---|
| `no files under ... match` | glob não casa nenhum arquivo | revisar `globs`/`glob` e `path_exclude` |
| `No results found.` | fonte não indexada ou `--in` com nome errado | `recall collections list` e repetir o passo 2 |
| `was indexed with ... re-run 'recall ingest --recreate'` | coleção criada com outro modelo | `recall ingest <projeto> --recreate` |
| `another process (recall-mcp?) has the embedded Qdrant store open` | lock exclusivo do store embutido | fechar o outro processo ou usar o [Qdrant servidor](04-qdrant-server.md) |
| `graph metadata unavailable` | `graphify` ausente, timeout ou erro | instalar o Graphify; o ingest continua sem grafo |
| `tree-sitter support for go is not installed` | gramáticas opcionais ausentes | reinstalar o CLI com `recall[code]` (runbook 01, passo 1); os arquivos foram indexados como janelas de linhas |
| `not pruning: some projects failed` | `--prune` não roda quando um projeto falhou na mesma execução | corrigir o erro listado e repetir |
| uma coleção de tópico removido não aparece como órfã | o diretório da fonte não existe ou ela não descobre nenhum tópico | conferir `root` e `glob` da fonte |
