# Runbook: Configurar recall-mcp (Claude Code / opencode)

**Quando usar:** expor `recall search` como tool MCP em Claude Code ou opencode.

## Pré-requisitos

- `recall-mcp` no PATH: `which recall-mcp` deve retornar um path
- Se não: `uv tool install --reinstall --from . recall` (instala `recall` + `recall-mcp` juntos)
- Qdrant rodando e ao menos uma collection indexada (`recall search "test"` deve retornar algo)

## Claude Code

Editar `~/.claude/settings.json` — adicionar dentro de `"mcpServers"`:

```json
{
  "mcpServers": {
    "recall": {
      "type": "stdio",
      "command": "recall-mcp"
    }
  }
}
```

Reiniciar Claude Code. Para verificar: pedir ao Claude `search recall docs for "authentication"` — deve chamar a tool `search_docs`.

## opencode

Editar `~/.config/opencode/opencode.jsonc` — adicionar dentro de `"mcp"`:

```jsonc
{
  "mcp": {
    "recall": {
      "type": "local",
      "command": ["recall-mcp"],
      "enabled": true
    }
  }
}
```

Reiniciar opencode. Tool disponível via `/recall` ou `@recall search_docs`.

## Verificar que o MCP está funcionando

```bash
# rodar recall-mcp manualmente — deve aguardar stdin (JSON-RPC)
recall-mcp
# Ctrl-C para sair
```

Sem erro no stderr = binário funcionando. O cliente (Claude Code / opencode) gerencia o processo.

## Troubleshooting

- **`recall-mcp: command not found`** → `uv tool install --reinstall --from . recall`; confirmar que `$(uv tool bin)` está no PATH (`export PATH="$(uv tool bin):$PATH"`).
- **MCP server crasha no startup** → `recall-mcp 2>&1` — erros vão para stderr; causa comum: `recall.toml` não encontrado (rodar de um dir sem recall.toml e sem `~/.config/recall/recall.toml`).
- **Tool disponível mas sem resultados** → Qdrant vazio ou collections não indexadas; `recall ingest --all` primeiro.
- **Resultados de projetos errados** → verificar `recall.toml` ativo: `find_config()` caminha de CWD pra cima; se Claude Code/opencode estiver com CWD num projeto com `recall.toml` local, esse config tem precedência.
- **`recall-mcp` não é um servidor HTTP** → correto. Usa stdio (JSON-RPC). Não há porta para abrir; o cliente gerencia o processo diretamente.

## Relacionado

- [local-ingest.md](local-ingest.md) — indexar projetos antes de usar o MCP
- [recover.md](recover.md) — Qdrant unreachable
