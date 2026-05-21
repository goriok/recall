# Embeddings

**TL;DR** — recall usa `nomic-embed-text` local via Ollama: 768 dims, open-weights, zero custo; chunks são truncados em 1500 chars antes do embed para evitar overflow silencioso.

## Intuição

Um embedding é uma função `f(texto) → ℝ^N` que mapeia texto para um ponto num espaço de N dimensões. Textos semanticamente similares ficam próximos nesse espaço (distância cosine pequena); textos sem relação ficam longe.

O que isso compra: uma query em linguagem natural e um chunk de documentação sobre o mesmo conceito ficam próximos **mesmo que não compartilhem palavras**. "Como o sistema valida tokens?" e um chunk sobre `JWTVerifier` têm alta similaridade, mesmo que "valida tokens" nunca apareça no chunk.

A qualidade do retrieval depende diretamente da qualidade do modelo de embedding. Modelos maiores (mais params, mais dims) capturam nuances melhores, mas custam mais para rodar.

## Como o recall faz

Implementado em `src/recall/embedder.py:1-20`.

```python
_MAX_CHARS = 1500  # nomic-embed-text: 2048 tokens (~4 chars/token) → margem segura

def embed(text: str, *, config: EmbeddingConfig) -> list[float]:
    client = ollama.Client(host=config.ollama_host)
    response = client.embed(model=config.model, input=text[:_MAX_CHARS])
    return response.embeddings[0]

def embed_batch(texts: list[str], *, config: EmbeddingConfig) -> list[list[float]]:
    return [embed(t, config=config) for t in texts]
```

`embed_batch` chama `embed` serialmente — não envia um batch de N textos em uma request. Decisão intencional (ver "Por que essa escolha").

O cliente é criado a cada chamada (`ollama.Client(host=...)`). Sem conexão persistente. Overhead negligível para o volume de chunks típico.

**Nota crítica**: a init correta é `ollama.Client(host=config.ollama_host)`, **não** `ollama.Client(options={"host": ...})`. A segunda forma é a API errada e falha silenciosamente (usa localhost independente do config). Esse padrão está documentado em `AGENTS.md`.

## Por que essa escolha

**`nomic-embed-text`** — open-weights (Apache 2.0), roda via Ollama sem configuração adicional, 768 dims. No benchmark MTEB (Massive Text Embedding Benchmark), atinge ~62 de média em tarefas de retrieval — comparável ao `text-embedding-ada-002` da OpenAI (~61) e bem abaixo do `text-embedding-3-large` (~64 com 3072 dims). Para documentação técnica em inglês e português, a diferença prática é pequena.

**768 dims** é um sweet spot:
- Storage: cada vetor ocupa `768 × 4 bytes = 3 KB`. 100K chunks → ~300 MB no Qdrant.
- Modelos com 1024+ dims (e.g. `mxbai-embed-large`) precisariam `recreate_collection` porque `VECTOR_SIZE = 768` está hardcoded em `src/recall/indexer.py:12`.
- 3072 dims (OpenAI large) → 4× o storage, 4× o tempo de busca no HNSW, só remoto.

**Truncation em 1500 chars**: `nomic-embed-text` aceita até 2048 tokens. Com ~4 chars/token, isso é ~8K chars. Por que 1500 e não 8000? Porque o cálculo `chars/token` varia muito para código (tokens curtos) vs prosa (tokens longos). 1500 chars é conservador e garante que nunca haverá silently truncated token no modelo. O comentário em `embedder.py:8` explica o raciocínio: `# nomic-embed-text actual context: 2048 tokens (nomic-bert). ~4 chars/token → 1500 chars is safe.`

**Serial em vez de batch real**: a API Ollama aceita arrays no campo `input`. No entanto, processar N textos longos numa única request pode gerar payload gigante e erro 413 ou OOM no servidor Ollama. Serial é ~2× mais lento para batches grandes, mas previsível e sem surpresas.

## Quando quebra

**Chunk > 1500 chars perde o tail silenciosamente** — sem warning, sem erro. O embed é feito nos primeiros 1500 chars. Se uma seção de 3000 chars tem a informação crucial na segunda metade, essa informação é invisível para buscas. Para detectar: `grep` por chunks grandes no indexer (não há logging hoje).

**Trocar de modelo** exige `recall ingest --recreate` em todas as collections — os vetores antigos têm dimensões diferentes (ou mesmo dimensão, mas espaço diferente). Trocar `nomic-embed-text` por `mxbai-embed-large` (1024 dims) sem recreate produz resultados absurdos (comparação entre vetores de espaços incompatíveis).

**Ollama não rodando** — `embed()` lança `httpx.ConnectError`. O `qdrant_guard.ensure_qdrant()` faz o auto-start do Qdrant, mas não há auto-start para Ollama. Ver [docs/runbooks/recover.md](../runbooks/recover.md).

## Relacionado

- [02-chunking.md](02-chunking.md) — tamanho do chunk determina o que chega ao embed
- [04-vector-search.md](04-vector-search.md) — cosine similarity pressupõe normalização que `nomic-embed-text` faz internamente
- [docs/runbooks/recover.md](../runbooks/recover.md) — Ollama unreachable, modelo ausente
