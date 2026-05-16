from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from recall.chunker import chunk_markdown
from recall.config import Config
from recall.confluence.client import ConfluencePage
from recall.embedder import embed_batch
from recall.indexer import VECTOR_SIZE, _collection_exists


def index_confluence_pages(
    pages: list[ConfluencePage],
    *,
    collection: str,
    config: Config,
    recreate: bool = False,
) -> int:
    """Chunk, embed and upsert Confluence pages into Qdrant. Returns chunk count."""
    client = QdrantClient(url=config.qdrant.url)

    if recreate or not _collection_exists(client, collection):
        client.recreate_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    all_chunks = []
    for page in pages:
        md = page.to_markdown()
        chunks = chunk_markdown(md, source=f"{page.space_key}/{page.title}", collection=collection)
        for chunk in chunks:
            chunk.id = chunk.id  # already deterministic
        all_chunks.extend(chunks)

    if not all_chunks:
        return 0

    vectors = embed_batch([c.text for c in all_chunks], config=config.embedding)

    points = [
        PointStruct(
            id=int(c.id, 16) % (2**63),
            vector=v,
            payload={
                "text": c.text,
                "source": c.source,
                "collection": collection,
                "heading": c.heading,
                "confluence_page_id": next(
                    (p.id for p in pages if f"{p.space_key}/{p.title}" == c.source), ""
                ),
            },
        )
        for c, v in zip(all_chunks, vectors)
    ]

    client.upsert(collection_name=collection, points=points)
    return len(points)
