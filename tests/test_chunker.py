import pytest
from recall.chunker import chunk_markdown, Chunk


def test_chunk_returns_list_of_chunks():
    text = "# Title\n\nSome content here.\n"
    chunks = chunk_markdown(text, source="foo.md", collection="test")
    assert isinstance(chunks, list)
    assert len(chunks) >= 1
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_has_required_fields():
    text = "# Hello\n\nWorld content.\n"
    chunks = chunk_markdown(text, source="hello.md", collection="docs")
    chunk = chunks[0]
    assert chunk.text
    assert chunk.source == "hello.md"
    assert chunk.collection == "docs"
    assert chunk.heading is not None


def test_chunk_splits_on_headings():
    text = "# Section A\n\nContent A.\n\n# Section B\n\nContent B.\n"
    chunks = chunk_markdown(text, source="f.md", collection="c")
    assert len(chunks) == 2
    assert "Content A" in chunks[0].text
    assert "Content B" in chunks[1].text


def test_chunk_preserves_heading_in_text():
    text = "# My Header\n\nBody text here.\n"
    chunks = chunk_markdown(text, source="f.md", collection="c")
    assert chunks[0].heading == "My Header"
    assert "My Header" in chunks[0].text


def test_chunk_skips_empty_sections():
    text = "# Empty\n\n# Has content\n\nSome text.\n"
    chunks = chunk_markdown(text, source="f.md", collection="c")
    assert len(chunks) == 1
    assert chunks[0].heading == "Has content"


def test_chunk_handles_no_headings():
    text = "Just a paragraph with no heading.\n"
    chunks = chunk_markdown(text, source="f.md", collection="c")
    assert len(chunks) == 1
    assert chunks[0].heading == ""


def test_chunk_id_is_deterministic():
    text = "# A\n\nContent.\n"
    c1 = chunk_markdown(text, source="f.md", collection="c")
    c2 = chunk_markdown(text, source="f.md", collection="c")
    assert c1[0].id == c2[0].id


def test_chunk_id_differs_for_different_sources():
    text = "# A\n\nContent.\n"
    c1 = chunk_markdown(text, source="a.md", collection="c")
    c2 = chunk_markdown(text, source="b.md", collection="c")
    assert c1[0].id != c2[0].id
