# Documentação do recall

## Runbooks

Procedimentos para seguir do início ao fim, na ordem em que costumam ser necessários.

| Runbook | Quando usar |
|---|---|
| [01 — Instalar o plugin e fazer o primeiro índice](runbooks/01-install-plugin-and-first-index.md) | primeira instalação no Claude Code, Hermes ou Antigravity |
| [02 — Operar o ingest](runbooks/02-operate-ingest.md) | registrar fontes, indexar, reindexar, limpar e buscar |
| [03 — Embeddings remotos](runbooks/03-remote-embeddings.md) | ajustar, confiar ou trocar o provedor de embeddings |
| [04 — Qdrant servidor](runbooks/04-qdrant-server.md) | subir o Qdrant local, mantê-lo após reinício ou usar um servidor remoto |
| [05 — Testar e publicar uma versão](runbooks/05-test-and-release.md) | alterar o `recall`, validar os plugins e lançar |

## Decisões de arquitetura

As decisões estão em [`madrs/`](madrs/README.md).
