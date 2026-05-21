# Vector Search

**TL;DR** — a busca converte a query em vetor, chama `query_points` no Qdrant por collection, merge os resultados por score, retorna top-k global; multi-collection é feito no cliente, não no servidor.

## Intuição

Dado um vetor de query `q` e um índice de N vetores, a busca retorna os K vetores mais próximos de `q`. "Próximo" é medido por cosine similarity:

```
cosine(a, b) = (a · b) / (|a| × |b|)
```

Resultado: 1.0 = vetores idênticos (mesma direção), 0.0 = ortogonais (sem relação), -1.0 = opostos. Para textos embedados com `nomic-embed-text` (internamente normalizado), scores ficam tipicamente entre 0.3 e 0.95 — valores abaixo de 0.4 geralmente são resultados irrelevantes.

Por que cosine em vez de distância euclidiana (L2)?

Cosine é invariante à **magnitude** do vetor. Um chunk longo e um chunk curto sobre o mesmo assunto têm vetores na mesma direção, mas magnitudes diferentes. Com L2, o chunk longo seria penalizado por "estar mais longe" no espaço. Com cosine, ambos ficam igualmente próximos de uma query relevante.

Qdrant usa HNSW (Hierarchical Navigable Small World) como índice — busca aproximada em O(log N) em vez de busca exata em O(N). Para até ~500K vetores num índice local, a diferença de recall entre exato e HNSW é negligível (<1%).

## Como o recall faz

Implementado em `src/recall/searcher.py:20-59`.

```python
def semantic_search(
    query: str,
    *,
    config: Config,
    collection: str | None = None,
    top_k: int = 5,
) -> list[SearchResult]:
    vector = embed(query, config=config.embedding)       # query → vetor
    client = QdrantClient(url=config.qdrant.url)

    collections = (
        [collection] if collection else [p.collection for p in config.projects]
    )

    results: list[SearchResult] = []
    for col in collections:
        try:
            response = client.query_points(             # API atual (≥ 1.9)
                collection_name=col,
                query=vector,
                limit=top_k,
                with_payload=True,
            )
            for hit in response.points:
                results.append(SearchResult(..., score=hit.score))
        except Exception:
            continue                                    # collection não indexada: skip

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]                             # top-k global
```

Cosine distance está configurada na criação da collection: `src/recall/indexer.py:24-28` usa `VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)`.

## Por que essa escolha

**`query_points` em vez de `client.search()`** — `client.search()` foi deprecated e removido no qdrant-client ≥ 1.9. Usar a API nova evita regressão silenciosa ao atualizar a dependência. Documentado em `AGENTS.md` ("Qdrant query API").

**Multi-collection merge no cliente** — em vez de distributed search no Qdrant, `searcher.py` itera collections e merge no Python. Simples, sem configuração de Qdrant adicional. Tradeoff: cada collection recebe o mesmo `limit=top_k` antes do merge global. Com 10 collections e `top_k=5`, o merge considera até 50 resultados e retorna os 5 melhores — razoável. Mas a collection maior pode contribuir com mais hits de alta confiança, "lavando" collections menores mesmo que tenham um resultado altamente relevante.

**`top_k = 5` default** — 5 chunks de ~500 chars = ~2500 chars de contexto no prompt do LLM. Balanço entre cobertura (mais resultados = mais chance de ter a resposta) e custo de contexto (mais texto = mais tokens no LLM). Configurável via parâmetro na MCP tool.

**Exception ignorada por collection** — se uma collection não existe (ainda não foi ingestada), `query_points` lança exceção. O `continue` garante que uma collection vazia não interrompe a busca nas demais.

## Quando quebra

**Collections com cardinalidade muito desigual** — uma collection com 50K chunks e outra com 50. Cada uma retorna seus top-5 antes do merge. A grande pode retornar 5 resultados com scores 0.85–0.90; a pequena retorna 5 com scores 0.75–0.80. Resultado final: todos os 5 vêm da coleção grande. A pequena nunca aparece no top-k global, mesmo que tenha a resposta certa. Workaround: chamar `semantic_search(query, collection="pequena", top_k=5)` explicitamente, ou aumentar o `limit` interno antes do merge (não configurável hoje).

**Query muito curta** — "auth" como query gera um vetor pobre. Queries descritivas em linguagem natural ("como o sistema autentica usuários via OAuth") dão vetores mais ricos e resultados melhores.

**Score threshold ausente** — não há filtro mínimo de score. Se nenhum resultado for relevante, os 5 piores ainda são retornados. O MCP retorna "No results found." apenas quando `results == []` (collection vazia), não quando os scores são todos baixos.

## Relacionado

- [03-embeddings.md](03-embeddings.md) — como o vetor de query é gerado
- [01-rag-pipeline.md](01-rag-pipeline.md) — contexto geral do pipeline
- [05-idempotency.md](05-idempotency.md) — como os vetores são armazenados com IDs determinísticos
- [docs/runbooks/recover.md](../runbooks/recover.md) — Qdrant unreachable
