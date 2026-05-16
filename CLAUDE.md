@AGENTS.md

# recall — Claude Code

## Important Constraints

- IMPORTANT: Always run `uv run pytest` before committing. Coverage must stay ≥ 90%.
- IMPORTANT: When patching in tests, patch at the *consumer* module, not the definition module.
- IMPORTANT: Qdrant and Ollama must be running locally for integration paths — check with `recall search "test"` before reporting a feature works end-to-end.
- IMPORTANT: `recall-mcp` is the MCP server binary — it communicates via stdio. Do not add HTTP transport.
