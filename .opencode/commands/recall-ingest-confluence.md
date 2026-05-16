# recall-ingest-confluence

Index Confluence pages into the local Qdrant vector store for semantic search.

## Usage

```bash
# Index an entire space
recall ingest-confluence --space ENG

# Index a specific page and all its children
recall ingest-confluence --page-id 123456

# Index all pages with a given label
recall ingest-confluence --label architecture

# Index all accessible pages
recall ingest-confluence --all

# Custom collection name + recreate
recall ingest-confluence --space ENG --collection eng-docs --recreate
```

## Requirements

- `[confluence]` section must exist in `recall.toml` or `~/.config/recall/recall.toml`
- Qdrant must be running (`podman compose up -d`)

## Example recall.toml snippet

```toml
[confluence]
url = "https://yourorg.atlassian.net"
auth_type = "token"
email = "{env:CONFLUENCE_EMAIL}"
token = "{env:CONFLUENCE_TOKEN}"
```

Set `CONFLUENCE_EMAIL` and `CONFLUENCE_TOKEN` in your environment (e.g. `.env` or shell profile).
