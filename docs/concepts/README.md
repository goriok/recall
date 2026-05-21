# Conceitos — recall

Documentação conceitual do recall: **por que** cada decisão foi tomada, quais premissas ela assume e quando quebra.

> **Quer fazer algo agora?** Vá para [docs/runbooks/](../runbooks/README.md).
> **Quer entender por quê?** Você está no lugar certo.

## Ordem de leitura

| # | Documento | O que cobre |
|---|---|---|
| 01 | [RAG Pipeline](01-rag-pipeline.md) | Arquitetura geral, fluxo end-to-end, por que tokenless |
| 02 | [Chunking](02-chunking.md) | Heading-based, sem overlap, tradeoffs vs sliding window |
| 03 | [Embeddings](03-embeddings.md) | nomic-embed-text, 768 dims, truncation, cosine |
| 04 | [Vector Search](04-vector-search.md) | Qdrant, query_points, multi-collection merge |
| 05 | [Idempotency](05-idempotency.md) | SHA-256 IDs, uint64 mod, upsert determinístico |
| 06 | [MCP Protocol](06-mcp-protocol.md) | FastMCP stdio, JSON-RPC, single-tool design |
| 07 | [Scheduling](07-scheduling.md) | croniter, asyncio.Task, no-state, GChat side-effects |

Leitura linear (01→07) dá o quadro completo. Cada doc é stand-alone, mas `01` define o vocabulário que os outros assumem.

## Glossário rápido

| Termo | Definição |
|---|---|
| **chunk** | Fragmento de texto de um documento, unidade mínima de indexação |
| **embedding** | Vetor de floats representando o significado semântico de um texto |
| **vector** | Array de N floats (aqui: 768) mapeado num espaço de alta dimensão |
| **collection** | Conjunto de vetores no Qdrant correspondente a um projeto |
| **cosine similarity** | Medida de similaridade entre vetores; 1.0 = idêntico, 0 = sem relação |
| **top-k** | Os K resultados mais similares à query |
| **upsert** | Insert-or-update: cria se não existe, sobrescreve se existe |
| **idempotência** | Repetir a operação N vezes dá o mesmo resultado que fazer 1 vez |
| **RAG** | Retrieval-Augmented Generation: contexto recuperado antes de gerar |
| **MCP** | Model Context Protocol: protocolo para expor tools a LLMs via JSON-RPC |

## Onde o código implementa cada conceito

```
src/recall/
├── chunker.py      → 02 Chunking, 05 Idempotency
├── embedder.py     → 03 Embeddings
├── indexer.py      → 01 RAG Pipeline, 04 Vector Search, 05 Idempotency
├── searcher.py     → 04 Vector Search
├── mcp_server.py   → 01 RAG Pipeline, 06 MCP Protocol
├── config.py       → 01 RAG Pipeline (auto-discover)
└── scheduler/      → 07 Scheduling
```
