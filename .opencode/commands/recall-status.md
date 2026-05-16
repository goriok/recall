---
description: Check Qdrant health and list indexed collections with point counts
---

Run: $(curl -s http://localhost:6333/collections 2>&1)

Parse and show:
- Whether Qdrant is healthy and responding
- Which collections exist and their approximate point counts
- Cross-reference against the projects defined in ~/sources/recall/recall.toml to flag any projects not yet ingested
