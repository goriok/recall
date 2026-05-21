# Chunking

**TL;DR** — recall divide documentos markdown em chunks por heading (H1/H2), sem overlap; a estrutura já presente no doc é usada como sinal de coerência semântica.

## Intuição

O modelo de embedding recebe um texto e retorna um vetor. Quanto maior o texto, mais "difuso" o vetor fica — representa uma média de muitos assuntos em vez de um assunto específico. O objetivo do chunking é produzir unidades semanticamente coesas, pequenas o suficiente para que o vetor capture um tópico preciso.

Documentos markdown bem escritos já resolvem esse problema: cada `##` delimita um tópico. Usar essa estrutura é mais barato e mais preciso do que cortar por número de tokens.

Por que não sliding window? Sliding window (e.g. 512 tokens, overlap de 128) é genérico — funciona bem para prosa densa (artigos, livros) onde não há divisões naturais. Para documentação técnica com headings, gera chunks que atravessam conceitos sem necessidade, aumentando ruído e custo de embed.

## Como o recall faz

Implementado em `src/recall/chunker.py:22-68`.

```python
pattern = re.compile(r"^(#{1,2} .+)$", re.MULTILINE)
parts = pattern.split(text)
```

`pattern.split(text)` com um grupo capturador alterna: `[pré-heading, heading, body, heading, body, ...]`. O texto antes do primeiro heading vira um chunk headingless (índice de arquivo, preamble).

Para cada par `(heading, body)`:

```python
full_text = f"{heading}\n\n{stripped}".strip() if heading else stripped
chunks.append(Chunk(
    id=_make_id(source, heading, index),
    text=full_text,        # heading prefixado no texto
    source=source,
    collection=collection,
    heading=heading.lstrip("#").strip(),
))
```

O heading é prefixado no `text` do chunk — o embedding "vê" o título junto com o conteúdo. Um chunk sobre "## Deploy Process" terá esse contexto codificado no vetor.

Seções vazias (`stripped == ""`) são puladas — não geram chunks nem IDs.

## Por que essa escolha

**Sem overlap** — overlap entre chunks duplica conteúdo no índice. Para docs estruturados onde cada seção é auto-contida, overlap só aumenta ruído. Tradeoff aceito: se uma ideia atravessa dois headings (e.g. um exemplo de código que continua depois do `##`), a segunda metade perde o contexto do parágrafo anterior.

**Só H1/H2** (não H3, H4...) — granularidade mais grossa. Docs com sub-seções profundas (H3 dentro de H2 dentro de H1) ficam em chunks maiores, mas evita over-segmentation onde seções H3 têm 2 linhas e o vetor captura quase nada. Tradeoff: seção H2 longa com múltiplos H3 vira um chunk grande → truncado em 1500 chars no embed step (ver [03-embeddings.md](03-embeddings.md)).

**Heading no texto do chunk** — sem isso, um chunk com heading "## Authentication" e corpo "Uses JWT tokens signed with RS256" teria o vetor representando só o corpo. Com o heading prefixado, a query "como funciona autenticação" tem mais chance de achar o chunk mesmo que o corpo não use a palavra "autenticação".

## Quando quebra

**Docs sem headings** — notas brutas, changelogs, transcrições de reuniões, README simples de uma linha. Todo o documento vira um único chunk. Se o doc tem > 1500 chars, o tail é silenciosamente truncado no embed. Workaround: pré-processar inserindo headings sintéticos, ou aceitar que docs não-estruturados têm retrieval de baixa qualidade.

**Seção única muito longa** — um `## API Reference` com 5000 chars de tabela de endpoints. O chunk é criado, mas o embed vê só os primeiros 1500 chars. A segunda metade da tabela é invisível para a busca. Workaround: `--recreate` não ajuda; a solução real é subdividir o doc ou trocar para token-based chunking com overlap para esse tipo de conteúdo.

**Posição muda após edição** — inserir uma nova seção no meio do arquivo muda o `index` de todas as seções seguintes, gerando IDs novos (ver [05-idempotency.md](05-idempotency.md)). Os chunks antigos ficam como órfãos no Qdrant até `--recreate`.

## Relacionado

- [03-embeddings.md](03-embeddings.md) — truncation de 1500 chars interage com tamanho do chunk
- [05-idempotency.md](05-idempotency.md) — heading e index entram no ID do chunk
- [docs/runbooks/local-ingest.md](../runbooks/local-ingest.md) — ingestar documentos locais
