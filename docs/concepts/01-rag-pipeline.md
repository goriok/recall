# RAG Pipeline

**TL;DR** — recall é um pipeline RAG tokenless: embeddings e busca rodam 100% locais (Ollama + Qdrant), sem chamadas externas pagas.

## Intuição

RAG (Retrieval-Augmented Generation) resolve um problema simples: LLMs não leem o seu codebase em tempo real. Quando você pergunta "como funciona o fluxo de autenticação do hyle?", o modelo adivinha com base no treinamento — que pode ter meses de defasagem e certamente não tem o seu código interno.

A solução clássica: antes de gerar, **recupere** os trechos relevantes e cole no contexto. O LLM responde com informação real, não alucinada.

Por que semântico em vez de full-text (`grep -r auth`)?

- `grep` exige que você saiba o termo exato. "Fluxo de autenticação" → `grep auth` funciona; "como o sistema valida identidade" → não.
- Embeddings capturam intenção, não tokens. A query "validação de identidade" é similar a um chunk sobre JWT mesmo que as palavras não batam.

## Como o recall faz

Dois fluxos separados: **ingest** (offline, periódico) e **search** (online, por chamada MCP).

```
INGEST
markdown files
    └─ chunker.py         split em seções por heading
        └─ embedder.py    cada chunk → vetor 768 floats (Ollama nomic-embed-text)
            └─ indexer.py upsert no Qdrant (collection por projeto)

SEARCH
query string
    └─ embedder.py        query → vetor 768 floats
        └─ searcher.py    query_points no Qdrant, merge multi-collection, top-k
            └─ mcp_server.py  formata resultado como markdown → retorna ao LLM
```

Entry points CLI: `src/recall/cli.py:1-35` (comandos `ingest`, `ingest-confluence`, `search`, `scheduler`).
Search surface exposta via MCP: `src/recall/mcp_server.py:11-55` (ferramenta `search_docs`).

## Por que essa escolha

**Tokenless**: nenhuma chamada sai da máquina durante busca. Ollama serve o modelo de embedding localmente; Qdrant é um processo local via `podman compose up -d`. Contrast: OpenAI `text-embedding-3-large` custa ~$0.13/1M tokens e exige internet.

**Local-first**: funciona offline, sem chave de API, sem GDPR preocupante (docs nunca saem do host). Tradeoff: `nomic-embed-text` (768 dims, MTEB ~62) é inferior ao `text-embedding-3-large` (3072 dims, MTEB ~64) — mas a diferença em retrieval prático para documentação técnica é pequena.

**Single-binary**: `uv tool install --from . recall` instala `recall` + `recall-mcp` juntos. Sem gerenciamento de virtualenv pelo usuário.

**Comparação com frameworks**: LangChain/LlamaIndex fazem o mesmo, com mais abstração. recall é mais simples por design — sem cadeia de abstrações, sem configuração de embedder/retriever em YAML. O pipeline inteiro cabe em ~5 arquivos Python.

## Quando quebra

**Queries temporais** — "o que mudou na última semana?" — embeddings semânticos não carregam noção de tempo. O chunk de "deploy process" de 2023 tem o mesmo score que o de 2024. Pivô: payload filtering por `mtime` no Qdrant (não implementado hoje) ou hybrid search com BM25 como tiebreaker.

**Documentação não-textual** — slides, PDFs complexos, diagramas. O pipeline só ingere texto. Workaround: exportar como markdown antes de ingestar.

**Collections muito grandes** — Qdrant local aguenta centenas de milhares de vetores numa máquina com 8GB RAM. Com coleções de milhões de chunks, o footprint de memória cresce; considerar HNSW tunning (`m`, `ef_construct`) no Qdrant.

## Relacionado

- [02-chunking.md](02-chunking.md) — como o markdown vira chunks
- [03-embeddings.md](03-embeddings.md) — como chunks viram vetores
- [04-vector-search.md](04-vector-search.md) — como a busca funciona
- [06-mcp-protocol.md](06-mcp-protocol.md) — como o resultado chega ao LLM
- [docs/runbooks/README.md](../runbooks/README.md) — colocar em prática
