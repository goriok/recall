# MADR-003: Repositórios de código, metadados de linha e embeddings remotos

**Status:** approved

## Contexto

O `recall` indexava só Markdown, fatiado por cabeçalhos, e gravava `source` como caminho absoluto. Um code-agent precisa receber na busca onde o trecho está (`file_path` relativo, `start_line`, `end_line`, `symbol_name`) para então ler e editar o arquivo real, mais contexto de arquitetura (comunidade, god node, símbolos relacionados).

Três limitações do código anterior moldaram a solução: o ID do ponto dependia de um índice posicional e o upsert nunca removia pontos órfãos; `OllamaEmbeddingProvider` cortava cada texto em 1500 caracteres e embedava um por vez (183,8 s para 32 chunks na CPU local); a busca sem filtro iterava só `config.projects`, que fica vazio com um `recall.toml` feito apenas de `[[sources]]`.

## Decisão

- **`[[repos]]` é um conceito separado de `[[sources]]`.** Um repo gera exatamente uma coleção `code.<name>`. Documentação continua em `[[sources]]` (uma coleção por tópico) e passa a gravar `file_path` relativo à raiz do repo de contexto, `start_line`/`end_line` e `breadcrumb`.
- **Linhas e símbolos vêm do chunker**, não do Graphify: Python por `ast` (função, método, classe, `<module>` por trecho contíguo), demais linguagens por janelas de linhas com overlap. O Graphify só enriquece o payload (`community_name`, `is_god_node`, `related_symbols`), casando por `(file_path, def_line)`.
- **Graphify é opcional.** Roda como subprocesso (`graphify update --force` e `graphify god-nodes --json`) com `GRAPHIFY_OUT` fora do repo indexado e `cwd=<root>`. Binário ausente, timeout ou erro degradam para ingest sem metadados de grafo, com aviso. Nenhuma chamada a LLM.
- **IDs estáveis, sem índice posicional.** Símbolos: `sha256(repo::file_path::qualname::k)`; Markdown: `sha256(repo::file_path::breadcrumb::k)`; janelas: pela posição da janela. `k` é a ordem de ocorrência do mesmo nome no arquivo.
- **Re-ingest reconcilia por arquivo.** O lote é embedado antes de apagar os pontos antigos do arquivo; arquivos que sumiram do disco têm seus pontos removidos (`distinct_values` menos arquivos existentes). `recall ingest --all --prune` remove coleções de tópicos que desapareceram.
- **`recall-meta`**: coleção separada, vetor constante `[1.0]`, um ponto por coleção (`uuid5` do nome) com `model_id` e `dimensions`; para repos de código guarda também o relatório do Graphify e os god nodes. A busca recusa uma coleção cujo modelo difere do provedor configurado. Coleção sem registro é tratada como legado `ollama:nomic-embed-text`/768 e reconstruída no próximo ingest.
- **Descoberta segura** (`discovery.py`): `git ls-files -z` quando há repo git (respeita `.gitignore`), `resolve().is_relative_to(root)`, denylist (`.env`, `*.pem`, `*.key`, `id_*`, `*credentials*`, `*secret*`), `max_file_bytes`, arquivos binários pulados e erro explícito quando nenhum arquivo casa.
- **Embeddings por um endpoint remoto compatível com OpenAI** (`OpenAIEmbeddingProvider`, por exemplo `nomic-embed-text-v1-5`, 768 dims): lote máximo de 32 (64+ devolve 400), retry com backoff só para 429/5xx, sem retry em 400/401/404, exceções sanitizadas (a chave nunca aparece em `str`/`repr`). O Ollama continua como padrão e como escolha para conteúdo pessoal; o provedor é configurável por `[[sources]]`/`[[repos]]`/`[[projects]]`.
- **Qdrant servidor** ganha `prefer_grpc`, `grpc_port`, `https` e `api_key_env`; `qdrant_guard` só sobe Podman para host local em http.
- **O MCP continua em stdio** nos dois escopos (embutido e servidor). Tools: `search_docs` (recusa `code.*`), `search_code` e `explain_architecture`.

## Consequências

**Positivas:**
- O agente recebe `repo_name`, `file_path` relativo e intervalo de linhas exatos; re-ingest é idempotente e não deixa órfãos; inserir uma função não muda o ID das vizinhas.
- Ingest ordens de grandeza mais rápido que o Ollama em CPU (medido: 582 chunks de código em 25 s incluindo o Graphify, contra ~5,7 s por chunk localmente).
- Containers e sandboxes não precisam de Ollama, só alcançar o endpoint.

**Negativas / custos:**
- Vetores de provedores diferentes não são comparáveis; trocar de provedor exige `recall ingest --recreate`, e uma busca ampla entre coleções de modelos distintos é recusada.
- O texto dos chunks sai da máquina para o endpoint nos repos que o usam; retenção e log das requisições dependem da política de quem opera o endpoint.
- Janelas de linhas (linguagens não-Python) mudam de ID quando linhas são inseridas acima; a reconciliação por arquivo evita órfãos.
- O Qdrant embutido mantém tudo em RAM e degrada além de ~20 mil pontos; o ingest avisa a partir de 15 mil.

## Segurança (adendo)

- `recall.toml` de projeto é entrada não confiável (`find_config` sobe a partir do diretório atual): `api_key_env` só é enviado para hosts declarados no `recall.toml` global, em `[security] trusted_hosts` ou em `RECALL_TRUSTED_HOSTS`, e hosts remotos exigem https. Sem isso um repo clonado poderia apontar `base_url` para um servidor próprio e ler qualquer variável de ambiente.
- A denylist de arquivos compara sem diferenciar maiúsculas de minúsculas e também confere o destino de symlinks.

## Empacotamento como plugin (adendo)

A skill `recall-search` vive em `skills/recall-search/SKILL.md` neste repositório e é compartilhada por todos os hosts: Claude Code (`.claude-plugin/`), Hermes (pacote portátil Agent Plugins v1: `plugin.json` + `mcp.json` na raiz) e `agy` (`plugins/recall/skills`, symlink). O Hermes repassa ao servidor MCP só um subconjunto seguro do ambiente (inclui `HOME`), por isso o próprio `recall` lê `~/.config/recall/.env`: apenas variáveis `RECALL_*` do arquivo global, nunca um `.env` do diretório atual. `RECALL_EMBEDDING_BASE_URL`, `RECALL_EMBEDDING_MODEL` e `RECALL_EMBEDDING_API_KEY` configuram o provedor sem que o endereço apareça em nenhum repositório; o host declarado ali é confiável para `recall.toml` locais.

O plugin entrega três skills, cada uma com gatilho e fluxo próprios: `recall-search` (docs e referência das tools), `recall-code` (navegar código a partir de `search_code`) e `recall-ingest` (configurar, indexar e diagnosticar). A tool MCP `list_sources` lista coleções, pontos, modelo, arquivos e data do último ingest (gravados no `recall-meta`), sem devolver caminhos absolutos, para que o agente descubra o que está indexado sem precisar de shell.

## Go, JavaScript e Rust (adendo)

Go (`.go`), JavaScript (`.js .mjs .cjs .jsx`) e Rust (`.rs`) passam a ser fatiados por símbolo via tree-sitter, em `treesitter_chunker.py`, com uma tabela por linguagem: funções, métodos (qualificados pelo tipo do receiver em Go, pela classe em JS, pelo tipo do `impl` em Rust), tipos (`struct`/`enum`/`interface`/`type`) e contêineres (classe JS, `impl`/`trait`/`mod` em Rust) tratados como header + membros + resto, o mesmo modelo das classes Python. Comentários de documentação, JSDoc e atributos Rust adjacentes entram no chunk do símbolo; `def_line` é a linha da declaração, que é a que o Graphify reporta.

As gramáticas são dependências opcionais (`recall[code]`). Sem elas, ou com separadores de linha incomuns, o arquivo cai para janelas de linhas com um aviso. `target/` e `vendor/` entram na exclusão padrão.

## Adiados

Reranker, `links_to`/`linked_from`, front matter e wikilinks, tree-sitter para TypeScript, Java, C e C++, e `qwen3-embedding-8b` ficaram fora desta entrega.
