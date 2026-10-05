# MADR-003: Repositórios de código, metadados de linha e embeddings remotos

**Status:** approved

## Contexto

O `recall` indexava só Markdown, fatiado por cabeçalhos, e gravava `source` como caminho absoluto. Um code-agent precisa receber na busca onde o trecho está (`file_path` relativo, `start_line`, `end_line`, `symbol_name`) para então ler e editar o arquivo real, mais contexto de arquitetura (comunidade, god node, símbolos relacionados).

Quatro limitações do código anterior moldaram a solução. O ID do ponto dependia de um índice posicional e o upsert nunca removia pontos órfãos. O `OllamaEmbeddingProvider` cortava cada texto em 1500 caracteres e embedava um por vez, com 183,8 s para 32 chunks na CPU local. A busca sem filtro iterava só `config.projects`, que fica vazio com um `recall.toml` feito apenas de `[[sources]]`. E um `recall.toml` de projeto é encontrado subindo a partir do diretório atual, ou seja, é entrada que quem clona um repositório não escreveu.

## Decisão

### Indexação de código

- **`[[repos]]` é um conceito separado de `[[sources]]`.** Um repo gera exatamente uma coleção `code.<name>`; documentação continua em `[[sources]]`, uma coleção por tópico.
- **Linhas e símbolos vêm do chunker, não do Graphify.** Python usa `ast` (função, método, classe, `<module>` por trecho contíguo); Go (`.go`), JavaScript (`.js .mjs .cjs .jsx`) e Rust (`.rs`) usam tree-sitter, em `treesitter_chunker.py`, com uma tabela por linguagem; as demais extensões viram janelas de linhas com overlap.
- **Comentários de documentação, JSDoc e atributos Rust** colados acima do símbolo fazem parte do chunk dele, e `def_line` é a linha da declaração sem eles, que é a que o Graphify reporta.
- **As gramáticas são dependências opcionais** (`recall[code]`). Sem elas, ou com separadores de linha incomuns, o arquivo cai para janelas de linhas com um aviso.
- **O Graphify é opcional.** Roda como subprocesso (`graphify update --force` e `graphify god-nodes --json`) com `GRAPHIFY_OUT` fora do repo indexado e `cwd=<root>`, casa por `(file_path, def_line)` e acrescenta `community_name`, `is_god_node` e `related_symbols`. Binário ausente, timeout ou erro degradam para ingest sem metadados de grafo, com aviso; nenhuma chamada a LLM.
- **Descoberta de arquivos segura** (`discovery.py`): `git ls-files -z` quando há repo git, `resolve().is_relative_to(root)`, `max_file_bytes`, binários pulados, erro explícito quando nenhum arquivo casa, e denylist (`.env`, `*.pem`, `*.key`, `id_*`, `*credentials*`, `*secret*`) que ignora maiúsculas e também confere o destino de symlinks. `target/` e `vendor/` entram na exclusão padrão.

### Chunking de Markdown

- Cada chunk grava `file_path` relativo à raiz do repositório de contexto, `start_line`, `end_line` e `breadcrumb` da pilha de cabeçalhos de h1 a h6; `text` é o texto cru das linhas indicadas e `embed_text` carrega o prefixo do breadcrumb.
- Cabeçalhos dentro de blocos de código cercados são ignorados, seções só com cabeçalho são descartadas e `max_chunk_chars` (padrão 4000) divide seções grandes por nível de cabeçalho, depois linha em branco, depois corte duro.

### Operação do ingest

- **IDs estáveis, sem índice posicional**: `repo::file_path::qualname::k` para símbolos e `repo::file_path::breadcrumb::k` para Markdown, com `k` a ordem de ocorrência do mesmo nome no arquivo.
- **Reconciliação por arquivo**: o lote é embedado antes de apagar os pontos antigos do arquivo, e arquivos que sumiram do disco têm seus pontos removidos.
- **`--prune` é conservador**: só considera órfã a coleção de uma fonte cujo diretório existe e ainda descobre tópicos, nunca toca `recall-meta` nem `code.*`, pede confirmação (`--yes` pula) e não roda se algum projeto falhou na mesma execução.
- **`recall-meta`** é uma coleção separada, com vetor constante `[1.0]` e um ponto por coleção (`uuid5` do nome), que guarda `model_id`, `dimensions`, `indexed_at` e `files`, e para repos de código o relatório do Graphify e os god nodes. A busca recusa uma coleção cujo modelo difere do provedor configurado; coleção sem registro vale como legado `ollama:nomic-embed-text`/768 e é reconstruída no próximo ingest.

### Embeddings remotos

- **`OpenAIEmbeddingProvider`** fala com qualquer endpoint `/embeddings` compatível com OpenAI: lote máximo de 32, retry com backoff exponencial só para 429/5xx, sem retry em 400/401/404, e exceções reescritas para que a chave nunca apareça em `str` ou `repr`. O Ollama continua como padrão e como escolha para conteúdo pessoal, e o provedor é configurável por `[[sources]]`, `[[repos]]` e `[[projects]]`.
- **Configuração fora dos repositórios**: `RECALL_EMBEDDING_BASE_URL`, `RECALL_EMBEDDING_MODEL` e `RECALL_EMBEDDING_API_KEY` (mais `RECALL_EMBEDDING_PROVIDER`, `RECALL_EMBEDDING_API_KEY_ENV` e `RECALL_EMBEDDING_BATCH_SIZE`) vêm do ambiente ou de `~/.config/recall/.env`. O `recall` lê desse arquivo só variáveis `RECALL_*` e nunca um `.env` do diretório atual; um `recall.toml` pode sobrescrever.
- **Qdrant servidor** ganha `prefer_grpc`, `grpc_port`, `https` e `api_key_env`; o `qdrant_guard` só sobe o Qdrant local para `http://localhost:6333`, via `QdrantService`, e `recall server enable` o mantém ligado entre reinícios com uma unit systemd de usuário.

### Confiança em `recall.toml` local

- Um `recall.toml` que não seja o global só pode usar um destino remoto (`base_url` de embeddings, `ollama_host` ou `host` do Qdrant) que o `.env` global, o `recall.toml` global, `[security] trusted_hosts` ou `RECALL_TRUSTED_HOSTS` já declarem, mesmo quando não há chave envolvida: sem isso um repo clonado poderia mandar todo o conteúdo indexado para um servidor dele.
- A variável de chave (`api_key_env`) só vale para um host se o arquivo global a associa a ele, o que impede um repo de escolher qual variável do ambiente enviar a um host confiável; hosts remotos exigem https quando há chave.
- As URLs são validadas de forma estrita: sem barra invertida, `@`, espaço ou caractere de controle, só host ASCII sem percent-encoding, e `urllib` e `httpx` precisam ler o mesmo host.

### Ferramentas MCP, skills e empacotamento

- O MCP continua em stdio nos dois escopos (Qdrant embutido e servidor) e expõe `search_docs` (recusa `code.*`), `search_code`, `explain_architecture` e `list_sources`, que lista coleções, pontos, modelo, arquivos e data do último ingest sem devolver caminhos absolutos.
- O plugin entrega três skills, cada uma com gatilho e fluxo próprios: `recall-search` (docs e referência das tools), `recall-code` (navegar código) e `recall-ingest` (configurar, indexar e diagnosticar).
- As skills vivem em `skills/` e são compartilhadas por todos os hosts: Claude Code (`.claude-plugin/`), Hermes (pacote portátil Agent Plugins v1 em `plugins/hermes/`, com cópia real das skills porque o Hermes copia o subdiretório e quebraria um symlink) e `agy` (`plugins/recall/skills`, um symlink). O pacote do Hermes fica fora da raiz porque o Hermes co-instala as dependências Python de qualquer plugin com `pyproject.toml` na raiz, e o `mcp<2` do recall conflita com o `mcp==2.0.0` dele. O Hermes repassa ao servidor MCP só um subconjunto seguro do ambiente, que inclui `HOME`, e por isso o próprio `recall` lê o `.env` global.

## Consequências

**Positivas:**
- O agente recebe `repo_name`, `file_path` relativo e intervalo de linhas exatos, o re-ingest é idempotente e não deixa órfãos, e inserir uma função não muda o ID das vizinhas.
- O ingest fica ordens de grandeza mais rápido que o Ollama em CPU (medido: 582 chunks de código em 25 s incluindo o Graphify, contra cerca de 5,7 s por chunk localmente).
- Containers e sandboxes não precisam de Ollama, só alcançar o endpoint.
- O endereço e a chave do endpoint não aparecem em nenhum repositório.

**Negativas / custos:**
- Vetores de provedores diferentes não são comparáveis: trocar o provedor exige `recall ingest --recreate`, e uma busca ampla entre coleções de modelos distintos é recusada.
- O texto dos chunks sai da máquina para o endpoint nos repos que o usam, e a retenção das requisições depende de quem opera o endpoint.
- Janelas de linhas (linguagens sem tree-sitter) mudam de ID quando linhas são inseridas acima; a reconciliação por arquivo evita órfãos.
- O Qdrant embutido mantém tudo em RAM e degrada além de cerca de 20 mil pontos; o ingest avisa a partir de 15 mil.
- Todo destino remoto de um `recall.toml` de projeto precisa ser declarado uma vez no lado global, o que é um passo a mais para quem usa um servidor remoto.

## Adiados

Reranker, `links_to`/`linked_from`, front matter e wikilinks, tree-sitter para TypeScript, Java, C e C++, e um modelo de embeddings maior ficaram fora desta entrega.
