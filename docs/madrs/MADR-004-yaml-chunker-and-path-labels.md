# MADR-004: Chunker YAML estrutural e rótulos de caminho para repos de IaC

**Status:** approved

## Contexto

Repos de infraestrutura como código (Helm/ArgoCD, por exemplo `magalu-cloud-iaas`: ~2000 arquivos YAML) caíam no fallback de janelas de 60 linhas do `chunk_code`. A janela corta blocos no meio (`image:` separado do seu `tag:`), não dá `symbol_name` e não carrega de qual ambiente, região e produto o trecho vem, embora o mesmo chart exista em várias combinações quase idênticas.

## Decisão

- **`yaml_chunker.py` fatia YAML por chave, sem dependência nova.** Um scanner por indentação (stdlib) reconhece linhas `chave:`; o PyYAML foi descartado porque falha em Helm/Go templating e não fornece linhas sem trabalho extra. Chave maior que `max_chunk_chars` desce um nível (`base-webapp.cronJob`), até 4 níveis; o cabeçalho da chave dividida vira span próprio. Chaves irmãs pequenas são agrupadas até 800 caracteres (`a..b`), sem cruzar `---`. Comentários colados acima da chave entram no span dela.
- **Fallback para janelas** quando o texto contém `{{` (template Helm) ou não tem nenhuma chave de mapeamento (listas, só comentários). Valor longo sem chaves filhas continua um span e é cortado por `_fit`.
- **`path_labels` por `[[repos]]`**: lista de templates de caminho (`{env}/{region}/service/{product}/{chart}/*`) tentados em ordem; o primeiro cujo número de segmentos e literais casa vira o prefixo `# env=prod region=ne1 ...` do `embed_text` (`path_labels.py`). O texto e o payload do chunk não mudam. Sem templates, o comportamento anterior é mantido.
- IDs seguem `repo::file_path::qualname::k`, portanto estáveis entre reingests.

## Consequências

- Busca por conceito de IaC devolve o bloco inteiro com o caminho da chave e o contexto de ambiente.
- Chunks quase idênticos entre ambientes continuam existindo; deduplicação e filtros por rótulo no payload ficam para depois, se o top-k saturar.
- O scanner não entende YAML de fluxo (`{a: 1}`) nem âncoras; esses trechos ficam dentro do bloco da chave pai.
