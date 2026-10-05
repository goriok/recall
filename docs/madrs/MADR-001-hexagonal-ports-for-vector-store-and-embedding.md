# MADR-001: Extrair portas VectorStore e EmbeddingProvider

**Status:** approved

## Contexto

`indexer.py`, `searcher.py` e `commands/collections.py` instanciavam `QdrantClient` e `ollama.Client` diretamente. Os testes cobriam esse código com `unittest.mock.patch` no símbolo importado (`patch("recall.indexer.QdrantClient")`), o que acopla o teste ao caminho exato do import e mistura teste de lógica de negócio real (ex.: filtro de `path_exclude`) com mock de infraestrutura no mesmo teste.

Hoje existe só um backend de vetor (Qdrant) e um provider de embedding (Ollama) — não há um segundo adapter real em vista. Pela referência de design hexagonal usada neste projeto (Cockburn, Ports & Adapters), isso normalmente seria motivo para NÃO extrair porta ainda ("extrair a porta quando o segundo adapter aparecer, não antes"). A motivação aqui é outra: testabilidade sem infraestrutura real (sem subir Qdrant/Ollama para rodar a suíte), não troca de tecnologia — motivo considerado válido à parte da regra do segundo adapter.

## Decisão

Extrair duas portas mínimas em `core/interfaces.py`:

- `VectorStore` (secondary/driven) — `collection_exists`, `recreate_collection`, `upsert`, `query`, `list_collections`, `delete_collection`. Cobre o uso real de `QdrantClient` em `indexer.py`, `searcher.py` e `commands/collections.py`.
- `EmbeddingProvider` (secondary/driven) — `embed`, `embed_batch`.

Tipos de domínio (`Point`, `VectorHit`, `CollectionInfo`) substituem os tipos do SDK do Qdrant (`PointStruct` etc.) na fronteira da porta, para a porta não vazar vocabulário de uma tecnologia específica.

Adapters únicos hoje: `QdrantVectorStore` (`adapters/qdrant_vector_store.py`), `OllamaEmbeddingProvider` (`adapters/ollama_embedding_provider.py`). `index_project` e `semantic_search` passam a receber as portas por parâmetro (injeção), em vez de instanciar a tecnologia concreta internamente. `commands/collections.py` idem.

Fora de escopo desta decisão: `qdrant_guard.py` (infraestrutura de processo/subida de container, não porta de domínio) e `confluence/*` (adapter já isolado, não vaza para a aplicação).

## Consequências

**Positivas:**
- Testes de `indexer.py`/`searcher.py`/`commands/collections.py` passam a usar fakes em memória (`FakeVectorStore`, `FakeEmbeddingProvider`) em vez de `mock.patch` de símbolo — mais robusto a refactoring interno do adapter.
- Um segundo backend de vetor ou embedding, se algum dia justificado, se encaixa sem tocar `indexer.py`/`searcher.py`.

**Negativas:**
- Indireção a mais (Protocol + adapter) para um projeto que ainda só tem um backend de cada — aceito conscientemente pelo motivo de testabilidade, não pela variação de tecnologia.
- Toda chamada em `commands/*.py`/`mcp_server.py` que hoje monta `config` precisa também montar e passar os adapters concretos — leve aumento de boilerplate na camada de aplicação.

## Atualização (0.5.0)

A decisão continua válida; o que mudou desde então está em [MADR-003](MADR-003-code-repos-line-metadata-and-remote-embeddings.md).

- A porta `VectorStore` ganhou `delete_where`, `distinct_values`, `scroll_where` e `count`, usados pela reconciliação por arquivo e pelo registro `recall-meta`.
- A porta `EmbeddingProvider` ganhou `model_id`, `dimensions` e `max_input_chars`, para fixar cada coleção ao modelo que a criou.
- Existe agora um segundo adapter de embeddings, `OpenAIEmbeddingProvider`, ao lado de `OllamaEmbeddingProvider`; o provedor é escolhido por projeto em `embeddings.py`.
- O módulo `confluence/*` citado em "Fora de escopo" não existe mais no código.

