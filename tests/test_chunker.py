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


def _chunks(text, **kwargs):
    return chunk_markdown(text, source="/abs/f.md", collection="c", file_path="topics/f.md", repo_name="repo", **kwargs)


def _lines(text):
    return text.splitlines()


def test_headings_inside_fenced_code_do_not_split():
    text = "# Title\n\nintro\n\n```bash\n# just a comment\n## also comment\n```\n\nafter\n"
    chunks = _chunks(text)
    assert len(chunks) == 1
    assert "just a comment" in chunks[0].text


def test_tilde_fences_and_longer_closing_fences_are_respected():
    text = "# T\n\n~~~\n# x\n~~~\n\n````\n# y\n```\n# still in fence\n````\n\n## Real\n\nbody\n"
    headings = [c.heading for c in _chunks(text)]
    assert headings == ["T", "Real"]


def test_unclosed_fence_swallows_rest_of_file():
    text = "# T\n\nbody\n\n```\n# not a heading\n"
    assert len(_chunks(text)) == 1


def test_line_numbers_are_one_indexed_and_roundtrip():
    text = "preamble\n\n# A\n\nbody a\n\n## B\n\nbody b\n"
    source_lines = _lines(text)
    chunks = _chunks(text)

    assert [(c.start_line, c.end_line) for c in chunks] == [(1, 1), (3, 5), (7, 9)]
    for c in chunks:
        assert "\n".join(source_lines[c.start_line - 1 : c.end_line]) == c.text


def test_breadcrumb_tracks_heading_stack():
    text = "# A\n\nx\n\n## B\n\ny\n\n### C\n\nz\n\n## D\n\nw\n"
    chunks = _chunks(text)
    assert [c.breadcrumb for c in chunks] == [["A"], ["A", "B"], ["A", "D"]]


def test_deeper_headings_stay_inside_chunk_by_default():
    text = "# A\n\n### Deep\n\ntext\n"
    chunks = _chunks(text)
    assert len(chunks) == 1
    assert "### Deep" in chunks[0].text


def test_header_only_sections_are_skipped():
    text = "# A\n\n## B\n\nbody\n\n# Empty\n"
    assert [c.heading for c in _chunks(text)] == ["B"]


def test_pre_heading_chunk_has_empty_heading_and_breadcrumb():
    chunks = _chunks("just text\n\n# H\n\nbody\n")
    assert chunks[0].heading == ""
    assert chunks[0].breadcrumb == []
    assert chunks[0].start_line == 1


def test_empty_text_yields_no_chunks():
    assert _chunks("") == []
    assert _chunks("\n\n  \n") == []


def test_crlf_text_is_handled():
    chunks = _chunks("# A\r\n\r\nbody\r\n")
    assert len(chunks) == 1 and chunks[0].start_line == 1


def test_file_path_mode_ids_are_stable_when_a_section_is_inserted():
    before = "# A\n\none\n\n# B\n\ntwo\n\n# C\n\nthree\n"
    after = "# A\n\none\n\n# New\n\ninserted\n\n# B\n\ntwo\n\n# C\n\nthree\n"
    ids_before = {c.heading: c.id for c in _chunks(before)}
    ids_after = {c.heading: c.id for c in _chunks(after)}
    assert ids_before["A"] == ids_after["A"]
    assert ids_before["B"] == ids_after["B"]
    assert ids_before["C"] == ids_after["C"]


def test_repeated_headings_get_distinct_ids():
    text = "# Same\n\none\n\n# Same\n\ntwo\n"
    ids = [c.id for c in _chunks(text)]
    assert len(set(ids)) == 2


def test_ids_depend_on_repo_and_file_path():
    text = "# A\n\nbody\n"
    a = chunk_markdown(text, source="s", collection="c", file_path="x.md", repo_name="r1")[0].id
    b = chunk_markdown(text, source="s", collection="c", file_path="y.md", repo_name="r1")[0].id
    c = chunk_markdown(text, source="s", collection="c", file_path="x.md", repo_name="r2")[0].id
    assert len({a, b, c}) == 3


def test_embed_text_carries_breadcrumb_but_text_stays_raw():
    chunk = _chunks("# A\n\n## B\n\nbody\n")[0]
    assert chunk.embed_text.startswith("# A > B\n\n")
    assert chunk.text.startswith("## B")
    assert not chunk.text.startswith("# A > B")


def test_max_chunk_chars_splits_at_deeper_headings():
    text = "# A\n\nintro\n\n### One\n\n" + "x" * 80 + "\n\n### Two\n\n" + "y" * 80 + "\n"
    chunks = _chunks(text, max_chunk_chars=120)
    assert len(chunks) == 3
    assert [c.breadcrumb[-1] for c in chunks] == ["A", "One", "Two"]
    assert all(len(c.text) <= 120 for c in chunks)


def test_max_chunk_chars_falls_back_to_blank_lines_then_hard_cut():
    paragraphs = "\n\n".join("p" * 40 for _ in range(6))
    chunks = _chunks(f"# A\n\n{paragraphs}\n", max_chunk_chars=100)
    assert len(chunks) > 1
    assert all(len(c.text) <= 100 for c in chunks)

    long_line = "# A\n\n" + "z" * 250 + "\n"
    cut = _chunks(long_line, max_chunk_chars=100)
    assert all(len(c.text) <= 100 for c in cut)
    assert "".join(c.text for c in cut if set(c.text) == {"z"}) == "z" * 250
    assert all(c.start_line == c.end_line == 3 for c in cut if set(c.text) == {"z"})


def test_split_chunks_keep_distinct_ids_even_with_same_breadcrumb():
    paragraphs = "\n\n".join("p" * 40 for _ in range(6))
    chunks = _chunks(f"# A\n\n{paragraphs}\n", max_chunk_chars=100)
    assert len({c.id for c in chunks}) == len(chunks)


def test_oversized_roundtrip_for_heading_split_pieces():
    text = "# A\n\nintro\n\n### One\n\n" + "x" * 80 + "\n\n### Two\n\n" + "y" * 80 + "\n"
    lines = text.splitlines()
    for c in _chunks(text, max_chunk_chars=120):
        assert "\n".join(lines[c.start_line - 1 : c.end_line]) == c.text


def test_header_only_intro_of_oversized_section_is_dropped():
    text = "# A\n\n### One\n\n" + "x" * 80 + "\n\n### Two\n\n" + "y" * 80 + "\n"
    chunks = _chunks(text, max_chunk_chars=120)
    assert [c.breadcrumb[-1] for c in chunks] == ["One", "Two"]
