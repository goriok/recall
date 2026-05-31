@AGENTS.md

# recall — Claude Code

## Important Constraints

- IMPORTANT: Always run `uv run pytest` before committing. Coverage must stay ≥ 90%.
- IMPORTANT: When patching in tests, patch at the *consumer* module, not the definition module.
- IMPORTANT: Qdrant and Ollama must be running locally for integration paths — check with `recall search "test"` before reporting a feature works end-to-end.
- IMPORTANT: `recall-mcp` is the MCP server binary — it communicates via stdio. Do not add HTTP transport.

## O que Nunca Fazer

- NUNCA use `pip install` — sempre `uv add`
- NUNCA commite sem rodar `uv run pytest` (cobertura deve permanecer ≥ 90%)
- NUNCA faça patch no módulo de definição — sempre no módulo consumidor
- NUNCA inicie `recall-mcp` com transporte HTTP — apenas stdio
- NUNCA reporte feature como funcionando sem testar `recall search "test"` end-to-end com Qdrant e Ollama rodando
