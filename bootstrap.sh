#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Checking uv..."
if ! command -v uv &>/dev/null; then
  echo "uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

echo "==> Checking ollama..."
if ! command -v ollama &>/dev/null; then
  echo "ollama not found. Install: https://ollama.com/download"
  exit 1
fi

echo "==> Pulling nomic-embed-text embedding model..."
ollama pull nomic-embed-text

echo "==> Installing recall CLI..."
uv tool install --from "$REPO_ROOT" recall --force --reinstall

echo "==> Installing global config..."
mkdir -p "$HOME/.config/recall"
if [ ! -f "$HOME/.config/recall/recall.toml" ]; then
  cp "$REPO_ROOT/recall.toml" "$HOME/.config/recall/recall.toml"
  echo "    created ~/.config/recall/recall.toml"
else
  echo "    ~/.config/recall/recall.toml already exists — skipping (edit manually if needed)"
fi

echo "==> Configuring opencode MCP..."
OPENCODE_CONFIG="$HOME/.config/opencode/opencode.jsonc"
if [ -f "$OPENCODE_CONFIG" ]; then
  if grep -q '"recall"' "$OPENCODE_CONFIG"; then
    echo "    recall MCP already in opencode config — skipping"
  else
    echo "    Add this to the \"mcp\" section of $OPENCODE_CONFIG:"
    echo '    "recall": { "type": "local", "command": ["recall-mcp"], "enabled": true }'
  fi
else
  echo "    opencode config not found at $OPENCODE_CONFIG — skipping"
fi

echo "==> Configuring Claude Code MCP..."
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
if [ -f "$CLAUDE_SETTINGS" ]; then
  if grep -q '"recall"' "$CLAUDE_SETTINGS"; then
    echo "    recall MCP already in Claude Code settings — skipping"
  else
    echo "    Add this to mcpServers in $CLAUDE_SETTINGS:"
    echo '    "recall": { "type": "stdio", "command": "recall-mcp" }'
  fi
else
  echo "    Claude Code settings not found at $CLAUDE_SETTINGS — skipping"
fi

echo ""
echo "Done. Run 'recall --help' to get started."
echo "Next steps:"
echo "  1. Edit ~/.config/recall/recall.toml to configure your projects"
echo "  2. recall ingest --all"
echo "  3. recall search \"your query\""
