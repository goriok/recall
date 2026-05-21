# MCP Protocol

**TL;DR** — recall expõe uma única tool (`search_docs`) via FastMCP sobre stdio; o cliente (Claude Code / opencode) gerencia o ciclo de vida do processo; stateless por design.

## Intuição

MCP (Model Context Protocol) é um protocolo JSON-RPC que padroniza como ferramentas externas se comunicam com LLMs. O cliente (Claude Code, opencode) lança o servidor como subprocesso e troca mensagens via stdin/stdout. O servidor declara suas *tools* (funções que o LLM pode chamar), *resources* (dados que o LLM pode ler), e *prompts* (templates).

Sem MCP, integrar `recall search` a um LLM exigiria código customizado por client. Com MCP, qualquer client compatível enxerga `search_docs` automaticamente.

## Como o recall faz

Implementado em `src/recall/mcp_server.py:1-55`.

```python
mcp = FastMCP("recall")

def search_knowledge(query: str, project: str | None = None, top_k: int = 5) -> str:
    """Core search logic — separated for testability."""
    config_path = find_config()
    config = load_config(config_path)
    ensure_qdrant(config.qdrant.url)
    results = semantic_search(query, config=config, collection=project, top_k=top_k)
    if not results:
        return "No results found."
    lines = []
    for r in results:
        lines.append(f"### [{r.collection}] {r.source} (score: {r.score:.2f})")
        lines.append(r.text)
        lines.append("")
    return "\n".join(lines)

@mcp.tool()
def search_docs(query: str, project: str | None = None, top_k: int = 5) -> str:
    """Search indexed project documentation semantically."""
    return search_knowledge(query, project=project, top_k=top_k)

def main() -> None:
    mcp.run(transport="stdio")
```

`search_knowledge` está separado de `search_docs` propositalmente: `search_docs` é decorado com `@mcp.tool()` (não testável diretamente sem server), enquanto `search_knowledge` é uma função Python pura que os testes chamam diretamente.

**Transporte stdio**: o client (Claude Code / opencode) lança `recall-mcp` como subprocesso e escreve requests JSON-RPC no stdin. O servidor lê, processa, escreve a resposta no stdout. O stderr fica livre para logs de diagnóstico (não interferem com o protocolo).

## Por que essa escolha

**Stdio em vez de HTTP** — HTTP exigiria porta fixa, processo persistente em background, e potencialmente autenticação. Stdio: o client gerencia o ciclo de vida (start/stop do processo junto com o próprio client), zero exposição de rede, sem configuração adicional. Tradeoff: uma instância do `recall-mcp` por client — não pode ser compartilhado entre múltiplos processos.

**Markdown-string return** — o retorno de `search_docs` é uma string markdown (`### [collection] source (score)` + texto do chunk). Isso funciona porque o consumidor é um LLM: markdown é seu formato nativo para processar e re-apresentar. Tradeoff: perde estrutura para processamento programático — um chamador máquina que quisesse filtrar por score precisaria parsear a string. Alternativa (não implementada): retornar JSON com lista de `{text, source, score}`.

**Single tool com parâmetros opcionais** — em vez de expor `search_hyle`, `search_confluence`, `search_docs_topk10`, etc., recall tem uma tool com `project=None` (busca global) e `top_k=5` (padrão configurável). Reduz a superfície de API: o LLM aprende a usar uma tool, não um catálogo.

**Stateless por chamada** — cada invocação de `search_docs` faz:
1. `find_config()` — walk CWD upward até encontrar `recall.toml`
2. `load_config()` — parse TOML
3. `ensure_qdrant()` — verifica se Qdrant está respondendo
4. `semantic_search()` — embed query + query_points

Não há cache de config entre calls. Custo: ~50ms de overhead por call (IO + 3 syscalls). Benefício: config reload automático sem reiniciar o server.

## Quando quebra

**Filtros além de `project`** — não há como filtrar por `heading`, `source` regex, ou score mínimo via parâmetros da tool. Um LLM que queira "só resultados do arquivo `auth.md`" não tem como expressar isso. Workaround hoje: pedir ao LLM para filtrar o resultado markdown. Pivô: adicionar `source_filter: str | None = None` à tool — breaking change na interface MCP (clients que hardcodearam a assinatura precisariam atualizar).

**`recall-mcp` não encontrado** — o client tenta `exec("recall-mcp")` e falha com `FileNotFoundError`. Causa comum: `$(uv tool bin)` não está no `$PATH` do environment onde o client é lançado (variável de ambiente vs PATH no shell interativo). Ver [docs/runbooks/mcp-setup.md](../runbooks/mcp-setup.md).

**Config não encontrado** — `find_config()` walk não acha `recall.toml`. O server lança `ConfigError`. O client reporta "MCP server crashed". Causa: Claude Code / opencode com CWD num diretório sem `recall.toml` subindo nem em `~/.config/recall/recall.toml`.

**`recall-mcp` não é HTTP** — alguns usuários tentam abrir `localhost:<porta>` esperando uma interface web. Não existe — o servidor só fala JSON-RPC via stdio e não escuta em nenhuma porta.

## Relacionado

- [04-vector-search.md](04-vector-search.md) — o que `search_docs` chama internamente
- [01-rag-pipeline.md](01-rag-pipeline.md) — contexto geral do pipeline
- [docs/runbooks/mcp-setup.md](../runbooks/mcp-setup.md) — configurar recall-mcp no Claude Code / opencode
