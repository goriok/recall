# MADR-002: Qdrant embutido (path=) como modo padrão

**Status:** approved

## Contexto

Até aqui, `recall` sempre falava com um Qdrant via servidor HTTP (`host`/`port`), subido automaticamente via Podman/`docker-compose.yml` quando não estava rodando (`qdrant_guard.py`). Isso funciona, mas exige Podman instalado e configurado, um arquivo `docker-compose.yml` acessível (ver histórico de bug corrigido em `qdrant_guard.py` — o fallback de descoberta desse arquivo não funcionava fora do clone do próprio `recall`), e um processo de container rodando em segundo plano indefinidamente.

Objetivo declarado para este projeto: instalar e usar `recall` (via plugin em Claude Code, hermes-tui, opencode) deve ser o mais transparente possível — sem passo manual de "subir infraestrutura" antes do primeiro uso.

`qdrant-client` (o SDK Python usado por `recall`) tem um modo embutido oficial (`QdrantClient(path=...)`) — mesma API do modo servidor, persistência em SQLite local, sem processo separado. Limitação confirmada no código-fonte: um lock exclusivo por diretório (`portalocker.LockFlags.EXCLUSIVE`), então só um processo pode ter aquele `path` aberto por vez; tentar abrir de um segundo processo falha com erro explícito ("already accessed by another instance... use Qdrant server instead"), não com corrupção silenciosa. Limite documentado de ~20.000 pontos por coleção antes de recomendarem migrar para servidor — muito acima do volume típico de um tópico de um repositório de contexto pessoal.

Levantamento do uso real no momento desta decisão: `recall-mcp` não estava configurado em nenhum projeto Claude Code (`mcpServers` vazio nos escopos checados) — o cenário de concorrência entre múltiplos processos (CLI + MCP simultâneos, ou múltiplas sessões MCP) era hipotético, não observado.

## Decisão

`QdrantConfig.path` (com default `~/.local/share/recall/qdrant`) é o modo padrão. `host`/`port` continuam suportados para quem precisar de acesso concorrente real — nesse caso `ensure_qdrant` (Podman/`docker-compose.yml`) continua sendo usado, agora só sob demanda.

`QdrantVectorStore` decide o modo pelo `QdrantConfig` recebido: `host is not None` → servidor; caso contrário → embutido, com o diretório criado automaticamente se não existir.

Ciclo de vida da conexão precisou ficar explícito por causa do lock exclusivo do modo embutido:
- Comandos CLI (`ingest`, `search`, `collections list/drop`) — processos de vida curta, mas agora chamam `vector_store.close()` em `finally` no fim do comando, em vez de depender do GC do Python para liberar o lock.
- `mcp_server.py` — processo de vida longa (um `recall-mcp` por sessão MCP). Antes instanciava `QdrantVectorStore` a cada chamada de `search_docs`; isso dependia do GC coletar a instância anterior a tempo de liberar o lock antes da próxima chamada — não determinístico. Agora o adapter é construído uma vez (singleton de módulo, `_get_adapters`) e reutilizado por todas as chamadas daquele processo.

## Consequências

**Positivas:**
- Instalar e usar `recall` não depende mais de Podman/container por padrão — só do `uv`/Python e Ollama (para embeddings), que já eram obrigatórios.
- `qdrant_guard.py`, `docker-compose.yml` e a dependência de Podman continuam existindo, mas viram opcionais — só entram em jogo se o dev configurar `host`/`port` explicitamente.
- Ciclo de vida de conexão explícito remove uma classe de flakiness (warnings de shutdown com `QdrantClient.__del__` observados durante a suíte de testes antes desta mudança).

**Negativas:**
- Sem acesso concorrente real entre processos — dois `recall-mcp` (ou CLI + MCP) apontando para o mesmo `path` ao mesmo tempo falham com erro explícito em vez de funcionar. Aceito conscientemente dado o uso real observado (nenhum uso concorrente hoje); se isso mudar, a correção é reconfigurar `[qdrant] host`/`port` no `recall.toml` — sem mudança de código.
- Um segundo processo de longa duração usando o mesmo storage (ex.: o scheduler daemon do worktree `worktree-recall-scheduler`, ainda não trazido para `main`) precisaria rodar em modo servidor, não embutido, se coexistir com um `recall-mcp` de sessão interativa.

## Atualização (0.5.0)

O modo embutido continua o padrão. Mudanças posteriores, registradas em [MADR-003](MADR-003-code-repos-line-metadata-and-remote-embeddings.md):

- `qdrant_guard.ensure_qdrant` só sobe o Qdrant para `http://localhost:6333`, e agora o faz com `QdrantService` (um `podman run`, sem `docker-compose.yml`); para qualquer outro host, porta ou https ele falha com uma mensagem. O container publica só em `127.0.0.1`, e o `docker-compose.yml` passou a ser opcional.
- `recall server start|stop|restart|status|logs` gerenciam esse container e `recall server enable|disable` instalam e removem uma unit systemd de usuário (`Restart=always`, com lingering) para que ele volte após reinício; os dados ficam no volume `recall_qdrant_data`.
- `[qdrant]` aceita `prefer_grpc`, `grpc_port`, `https` e `api_key_env`.
- Um `recall ingest` com o `recall-mcp` aberto no mesmo store embutido termina com uma mensagem que aponta para o modo servidor.
- O ingest avisa quando uma coleção passa de 15 mil pontos, antes do limite de cerca de 20 mil.

