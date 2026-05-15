from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    collection: str
    heading: str


def _make_id(source: str, heading: str, index: int) -> str:
    key = f"{source}::{heading}::{index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def chunk_markdown(text: str, *, source: str, collection: str) -> list[Chunk]:
    """Split markdown into chunks on heading boundaries.

    Each heading (# or ##) starts a new chunk. Text before the first heading
    is treated as a headingless chunk. Empty sections are skipped.
    """
    # Split on lines that start with one or two #
    pattern = re.compile(r"^(#{1,2} .+)$", re.MULTILINE)
    parts = pattern.split(text)

    chunks: list[Chunk] = []
    index = 0

    # parts alternates: [pre-heading-text, heading, body, heading, body, ...]
    # When text starts with a heading, pre-heading-text is empty string
    i = 0
    current_heading = ""
    current_body = parts[0] if parts else ""

    def flush(heading: str, body: str) -> None:
        nonlocal index
        stripped = body.strip()
        if not stripped:
            return
        full_text = f"{heading}\n\n{stripped}".strip() if heading else stripped
        chunks.append(
            Chunk(
                id=_make_id(source, heading, index),
                text=full_text,
                source=source,
                collection=collection,
                heading=heading.lstrip("#").strip(),
            )
        )
        index += 1

    flush(current_heading, current_body)

    # Walk remaining pairs: (heading, body)
    i = 1
    while i < len(parts) - 1:
        heading = parts[i]
        body = parts[i + 1]
        flush(heading, body)
        i += 2

    return chunks
