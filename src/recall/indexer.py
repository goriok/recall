from __future__ import annotations

from recall.chunker import chunk_markdown
from recall.config import Config, ProjectConfig
from recall.core.interfaces import EmbeddingProvider, Point, VectorStore

VECTOR_SIZE = 768  # nomic-embed-text output dimensions


def index_project(
    project: ProjectConfig,
    *,
    config: Config,
    vector_store: VectorStore,
    embedding_provider: EmbeddingProvider,
    recreate: bool = False,
) -> int:
    """Index all markdown files for a project. Returns number of chunks indexed."""
    if recreate or not vector_store.collection_exists(project.collection):
        vector_store.recreate_collection(project.collection, VECTOR_SIZE)

    source_path = project.resolved_path
    if not source_path.exists():
        return 0

    blocked = set(project.path_exclude)
    files = [
        f for f in source_path.glob(project.glob)
        if not any(part in blocked for part in f.parts)
    ]

    all_chunks = []
    for file in files:
        try:
            text = file.read_text(encoding="utf-8")
            chunks = chunk_markdown(text, source=str(file.resolve()), collection=project.collection)
            all_chunks.extend(chunks)
        except Exception:
            continue

    if not all_chunks:
        return 0

    texts = [c.text for c in all_chunks]
    vectors = embedding_provider.embed_batch(texts)

    points = [
        Point(
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

    vector_store.upsert(project.collection, points)
    return len(points)
