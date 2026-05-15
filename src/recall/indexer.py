from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from recall.chunker import chunk_markdown
from recall.config import Config, ProjectConfig
from recall.embedder import embed_batch

VECTOR_SIZE = 768  # nomic-embed-text output dimensions


def index_project(
    project: ProjectConfig,
    *,
    config: Config,
    recreate: bool = False,
) -> int:
    """Index all markdown files for a project. Returns number of chunks indexed."""
    client = QdrantClient(url=config.qdrant.url)

    if recreate or not _collection_exists(client, project.collection):
        client.recreate_collection(
            collection_name=project.collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    source_path = project.resolved_path
    files = list(source_path.glob(project.glob))

    all_chunks = []
    for file in files:
        try:
            text = file.read_text(encoding="utf-8")
            rel = str(file.relative_to(source_path))
            chunks = chunk_markdown(text, source=rel, collection=project.collection)
            all_chunks.extend(chunks)
        except Exception:
            continue

    if not all_chunks:
        return 0

    texts = [c.text for c in all_chunks]
    vectors = embed_batch(texts, config=config.embedding)

    points = [
        PointStruct(
            id=int(c.id, 16) % (2**63),  # qdrant needs uint64
            vector=v,
            payload={
                "text": c.text,
                "source": c.source,
                "collection": c.collection,
                "heading": c.heading,
            },
        )
        for c, v in zip(all_chunks, vectors)
    ]

    client.upsert(collection_name=project.collection, points=points)
    return len(points)


def _collection_exists(client: QdrantClient, name: str) -> bool:
    try:
        client.get_collection(name)
        return True
    except Exception:
        return False
