---
name: recall-search
description: Busca semântica via recall (Qdrant + embeddings Ollama ou um endpoint remoto compatível com OpenAI) sobre documentação e código já indexados, com arquivo, intervalo de linhas e símbolo exatos. Use antes de grep/leitura manual quando a pergunta é conceitual e a localização exata do conteúdo não é óbvia.
globs: ["**/*"]
---

# Busca semântica local (recall)

`recall` indexa Markdown e código de projetos configurados em `~/.config/recall/recall.toml` num Qdrant (embutido ou servidor; embeddings via Ollama `nomic-embed-text` ou um endpoint remoto compatível com OpenAI, por projeto), uma collection por projeto de docs e uma `code.<repo>` por repositório de código. Prefira isto a
grep quando a pergunta é conceitual ("como funciona X", "onde decidimos Y") e não se sabe de
antemão em qual arquivo a resposta está — não é específico de nenhum repositório em particular,
qualquer projeto pode estar indexado.

Ferramenta e skill vivem no mesmo repositório: [goriok/recall](https://github.com/goriok/recall). Instalando o plugin `recall` (Claude Code, Hermes ou agy) você recebe esta skill junto com o servidor MCP `recall-mcp`.

## Comando

```bash
recall search "<query em linguagem natural>" --in <collection> --top 5
```

- `--in <collection>` restringe a uma collection — omitir para buscar em todas as configuradas
  (ranking por score global, sem normalização entre collections).
- `--top N` controla quantos chunks retornam (default 5).
- Query em português ou inglês, frase livre — não precisa ser palavra-chave exata.

## Descobrir o que está indexado

Não presumir nomes de collection — verificar antes de usar `--in`:

```bash
recall collections list
```

Lista todas as collections do Qdrant com contagem de vetores. Rodar uma busca sem `--in`
primeiro também é uma forma válida de descobrir onde o conteúdo relevante está, já que o
resultado traz a collection de origem de cada chunk.

`--in` com nome de collection errado ou inexistente não gera erro — retorna silenciosamente
`No results found.` (o searcher ignora exceções por collection ausente). Se uma busca que
deveria achar algo vier vazia, conferir o nome exato antes de concluir que o conteúdo não existe.

## Ferramentas MCP (`recall-mcp`)

- `search_docs(query, project?, top_k?, min_score?)` busca documentação e recusa collections `code.*`.
- `search_code(query, repo?, top_k?, min_score?)` busca código; cada resultado traz `repo`, `file_path` relativo à raiz do repo, intervalo `start-end`, `symbol`, `community`, `god_node` e `related`. Resolva `file_path` contra o checkout local do repo antes de ler ou editar as linhas indicadas.
- `explain_architecture(repo)` devolve os god nodes e o relatório do Graphify de um repo configurado.
- `list_sources()` lista o que está indexado (coleções, repos, pontos, modelo, data do último ingest) e avisa quando o modelo configurado difere do usado no índice. Chame primeiro quando não souber os nomes de projeto ou repo.

Para navegar código (localizar símbolo, impacto de uma mudança) use a skill `recall-code`; para indexar uma fonte nova ou diagnosticar uma busca vazia, a skill `recall-ingest`.

## Como interpretar o resultado

Resultados de documentação trazem `file_path:linhas` (relativo à raiz do repositório de contexto) e a linha `section:` com o breadcrumb de cabeçalhos; coleções antigas, ainda sem esses campos, mostram o `source` absoluto. O trecho é o texto cru das linhas indicadas.

Cada resultado retorna o `source` (path absoluto do arquivo original) ou o `file_path` e o texto do chunk
(heading + corpo). Sempre citar/abrir o arquivo fonte antes de usar o conteúdo como base de
geração — o chunk não carrega metadado do documento (como um campo de status, se o projeto usar
um), então confirmar diretamente no arquivo qualquer convenção de confiabilidade que o projeto
indexado use antes de tratar o conteúdo como definitivo.

## Quando NÃO usar

- Pergunta sobre estrutura/pastas em si (não conteúdo) — usar `ls`/`find` direto.
- Precisa do texto exato/grep de um termo específico (ID, nome de arquivo, string literal) —
  `grep -r` é mais preciso que busca semântica para isso.
- Índice pode estar desatualizado após edição recente no projeto fonte — rodar
  `recall ingest <nome>` (ou `--all`) para reindexar (idempotente: troca os chunks de arquivos alterados e remove os de arquivos apagados). Ao trocar o provedor de embeddings de uma collection, usar `--recreate`.

## Pré-requisito

No modo embutido (padrão) não há servidor para subir, mas só um processo por vez abre o store: fechar o `recall-mcp` antes de `recall ingest` ou usar Qdrant servidor. Em modo servidor local (http em `localhost`), `recall search`/`recall ingest` sobem o Qdrant sozinhos via `podman compose up -d`. Com embeddings remotos, a chave vai em `RECALL_EMBEDDING_API_KEY` no `~/.config/recall/.env`. Se um projeto ainda não está configurado
no `recall.toml`, ele não aparece na busca — configurar é fora do escopo desta skill.

## Ambiente do servidor MCP

O `recall-mcp` lê `~/.config/recall/.env` (apenas variáveis `RECALL_*`), então o endpoint e a chave de embeddings remotos ficam ali e valem igualmente no Claude Code, no Hermes (que filtra o ambiente do servidor MCP) e no agy.

Um `recall.toml` de projeto é tratado como não confiável: ele só pode usar um endpoint remoto (embeddings ou Qdrant) que o `.env` global (`RECALL_EMBEDDING_BASE_URL`), o `recall.toml` global, `[security] trusted_hosts` ou `RECALL_TRUSTED_HOSTS` já declarem, e só com a variável de chave que o arquivo global associa àquele host. Se a busca falhar com "refusing to talk to untrusted host" ou "is not authorized for", é essa trava.
