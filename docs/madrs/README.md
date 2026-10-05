# MADRs — recall

Decisões arquiteturais reais sobre o projeto `recall` — não notas de investigação, só decisões
de fato tomadas.

| MADR | Status | Resumo |
|---|---|---|
| [MADR-001](MADR-001-hexagonal-ports-for-vector-store-and-embedding.md) | approved | Extrair portas `VectorStore`/`EmbeddingProvider` para testabilidade sem infraestrutura real, sem troca de tecnologia em vista |
| [MADR-002](MADR-002-embedded-qdrant-by-default.md) | approved | Qdrant embutido (`path=`) como modo padrão — remove Podman/container do caminho de instalação padrão |
| [MADR-003](MADR-003-code-repos-line-metadata-and-remote-embeddings.md) | approved | Repos de código (`[[repos]]`), metadados de linha, Graphify opcional, `recall-meta`, embeddings remotos e chunking tree-sitter de Go/JS/Rust |
