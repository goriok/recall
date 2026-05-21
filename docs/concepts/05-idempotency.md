# Idempotency

**TL;DR** — cada chunk tem ID determinístico (`sha256(source::heading::index)[:16]`), convertido para uint64 via `mod 2^63`; upsert no Qdrant é no-op para conteúdo não modificado — reingest é sempre seguro.

## Intuição

Sem IDs determinísticos, cada execução de `recall ingest` criaria novos pontos no Qdrant para os mesmos chunks. Após 3 reingestas, a collection teria 3 cópias de cada chunk, scores duplicados nos resultados, e crescimento sem limite de storage.

Idempotência resolve isso: se o arquivo não mudou, o chunk produz o mesmo ID, e o `upsert` sobrescreve o ponto existente com dados idênticos — custo mínimo, sem duplicação.

## Como o recall faz

**Geração do ID** — `src/recall/chunker.py:17-19`:

```python
def _make_id(source: str, heading: str, index: int) -> str:
    key = f"{source}::{heading}::{index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

Componentes da chave:

- `source` — caminho absoluto do arquivo (e.g. `/home/alves.igor/sources/hyle/docs/auth.md`)
- `heading` — texto do heading do chunk (e.g. `## JWT Verification`)
- `index` — posição ordinal do chunk no arquivo (0, 1, 2, ...)

SHA-256 produz 64 hex chars (256 bits). Truncamos para 16 hex chars (64 bits). Probabilidade de colisão para 10^9 chunks: ≈ 1 − e^(−N²/2^64) ≈ 2^-32 — negligível.

**Conversão para uint64** — `src/recall/indexer.py:57`:

```python
id=int(c.id, 16) % (2**63),  # qdrant needs uint64
```

Qdrant aceita uint64 completo (0 a 2^64−1). O `mod 2^63` é uma salvaguarda: algumas libs cliente (Java, Kotlin) tratam IDs como int64 com sinal e entram em overflow para valores > 2^63−1. Cap em 2^63 garante que o ID é válido em qualquer client.

**Upsert em batches** — `src/recall/indexer.py:69-71`:

```python
batch_size = 100
for i in range(0, len(points), batch_size):
    client.upsert(collection_name=project.collection, points=points[i : i + batch_size])
```

`upsert` cria ou sobrescreve. Se o ID já existe com os mesmos dados, o Qdrant atualiza o ponto — operação cara de IO mas semanticamente no-op para o retrieval.

## Por que essa escolha

**`source::heading::index` como chave** — os três campos juntos identificam unicamente um chunk num arquivo: mesmo arquivo (`source`), mesma seção (`heading`), mesma posição (`index`). Se a seção for renomeada (`heading` muda), novo ID é gerado — comportamento correto, o chunk é semanticamente diferente. Se o conteúdo mudar mas o heading não, o ID é o mesmo e o upsert sobrescreve com o novo vetor.

**Por que `index` e não hash do conteúdo?** — hash do conteúdo (`sha256(text)`) seria mais robusto para detectar mudanças reais (evitaria upsert desnecessário). Mas torna o ID dependente do conteúdo atual, o que complica o debug ("por que esse chunk tem esse ID?"). Com `source::heading::index`, o ID é derivável só do arquivo e da estrutura — não precisa embedar para saber qual ID será gerado.

**16 hex chars (64 bits)** — 32 chars seria mais seguro contra colisão, mas Qdrant armazena IDs como uint64 de qualquer forma. 16 chars é o mínimo que faz sentido truncar para caber em uint64 (16 hex = 64 bits).

**Batch de 100** — balanço entre número de round-trips para collections grandes e tamanho do payload por request. 100 pontos de 768 floats = ~307 KB por batch — dentro do limite padrão do Qdrant.

## Quando quebra

**Renomear o arquivo** — `source` muda (caminho absoluto diferente). Todos os IDs mudam. O Qdrant mantém os pontos antigos (IDs diferentes) e cria novos pontos. Collection fica com duplicatas até `recall ingest --recreate`. Workaround: sempre fazer `--recreate` após mover ou renomear arquivos de fonte.

**Inserir seção no meio** — se um doc tem 10 chunks e uma nova seção é inserida entre chunk 3 e 4, os chunks 4–10 recebem `index` +1. IDs novos para todos eles. Os antigos ficam como órfãos. Mesmo comportamento do rename — `--recreate` resolve.

**Heading duplicado** — se um arquivo tem dois `## Instalação`, os dois geram a mesma chave (`source::## Instalação::0` para o primeiro, `source::## Instalação::1` para o segundo se index for diferente — espera, index é global, então são `index=2` e `index=5` por exemplo — na verdade heading duplicado não causa problema, pois `index` é monotônico no arquivo). Verificar: `chunker.py:40-56` mostra que `index` é incrementado por chunk independentemente do heading.

## Relacionado

- [02-chunking.md](02-chunking.md) — `heading` e `index` que entram no ID são gerados pelo chunker
- [04-vector-search.md](04-vector-search.md) — pontos armazenados via upsert são recuperados via `query_points`
- [docs/runbooks/local-ingest.md](../runbooks/local-ingest.md) — uso de `--recreate` para forçar rebuild
