from __future__ import annotations

from recall.code_chunker import chunk_code

SOURCE = '''import os

X = "initial module level value that is long enough to keep"


@decorator
def top(a):
    def inner():
        return 1
    return inner


class Service:
    """doc"""
    attr = 1

    def run(self):
        return 1

    other = 2

    @property
    def name(self):
        return "x"


def top(a):
    return 2


if TYPE_CHECKING:
    def conditional(): ...
else:
    def conditional(): pass

LAST_VALUE = "a module level constant that is long enough to keep"
'''


def _chunk(text=SOURCE, path="pkg/mod.py", **kwargs):
    params = {"file_path": path, "repo_name": "repo", "max_chars": 4000, **kwargs}
    return chunk_code(text, **params)


def _by_symbol(chunks):
    out = {}
    for c in chunks:
        out.setdefault(c.symbol_name, []).append(c)
    return out


def test_python_symbols_have_exact_one_indexed_line_ranges():
    lines = SOURCE.splitlines()
    symbols = _by_symbol(_chunk())

    top = symbols["top"][0]
    assert lines[top.start_line - 1] == "@decorator"
    assert lines[top.def_line - 1].startswith("def top")
    assert top.start_line == 6 and top.def_line == 7
    assert top.end_line == 10

    run = symbols["Service.run"][0]
    assert lines[run.def_line - 1].strip() == "def run(self):"
    assert lines[run.start_line - 1] == lines[run.def_line - 1]

    prop = symbols["Service.name"][0]
    assert lines[prop.start_line - 1].strip() == "@property"
    assert prop.def_line == prop.start_line + 1


def test_text_is_raw_source_lines_and_embed_text_has_header():
    lines = SOURCE.splitlines()
    for c in _chunk():
        assert c.text == "\n".join(lines[c.start_line - 1 : c.end_line])
        assert c.embed_text.startswith(f"# pkg/mod.py:{c.start_line}-{c.end_line}")
        assert c.text in c.embed_text


def test_nested_functions_stay_inside_their_parent_chunk():
    symbols = _by_symbol(_chunk())
    assert "inner" not in symbols and "top.inner" not in symbols
    assert "def inner" in symbols["top"][0].text


def test_class_with_methods_does_not_duplicate_method_text():
    symbols = _by_symbol(_chunk())
    header = symbols["Service"][0]
    assert "def run" not in header.text
    assert "attr = 1" in header.text
    rest = symbols["Service.<resto>"][0]
    assert rest.text.strip() == "other = 2"
    assert rest.kind == "class_rest"


def test_class_without_methods_is_a_single_chunk():
    chunks = _chunk("class A:\n    x = 1\n    y = 2\n")
    assert [(c.symbol_name, c.kind) for c in chunks] == [("A", "class")]


def test_redefined_functions_and_conditional_defs_get_distinct_ids():
    chunks = _chunk()
    symbols = _by_symbol(chunks)
    assert len(symbols["top"]) == 2
    assert len(symbols["conditional"]) == 2
    assert len({c.id for c in chunks}) == len(chunks)


def test_module_level_code_becomes_contiguous_module_chunks():
    modules = [c for c in _chunk() if c.kind == "module"]
    assert modules[0].text.startswith("import os")
    assert modules[0].end_line == 3
    assert all(c.def_line is None for c in modules)
    assert modules[-1].text.startswith("LAST_VALUE")


def test_ids_survive_insertion_above_for_python_symbols():
    before = _by_symbol(_chunk())
    shifted = _by_symbol(_chunk("# new comment\nimport sys\n" + SOURCE))
    assert before["Service.run"][0].id == shifted["Service.run"][0].id
    assert before["top"][0].id == shifted["top"][0].id
    assert before["Service.run"][0].start_line != shifted["Service.run"][0].start_line


def test_ids_depend_on_repo_and_path():
    a = _by_symbol(_chunk(repo_name="r1"))["top"][0].id
    b = _by_symbol(_chunk(repo_name="r2"))["top"][0].id
    c = _by_symbol(_chunk(path="other.py"))["top"][0].id
    assert len({a, b, c}) == 3


def test_syntax_error_falls_back_to_windows(caplog):
    broken = "def broken(:\n    pass\n" + "x = 1\n" * 10
    chunks = _chunk(broken, window_lines=5, window_overlap=1)
    assert chunks and all(c.kind == "window" for c in chunks)
    assert "falling back" in caplog.text


def test_non_python_files_use_overlapping_windows():
    text = "\n".join(f"line {i}" for i in range(1, 26))
    chunks = _chunk(text, path="main.go", window_lines=10, window_overlap=2)
    spans = [(c.start_line, c.end_line) for c in chunks]
    assert spans == [(1, 10), (9, 18), (17, 25)]
    assert all(c.symbol_name == "" and c.def_line is None for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_blank_windows_and_empty_files_are_skipped():
    assert _chunk("", path="a.go") == []
    assert _chunk("\n\n\n", path="a.py") == []
    text = "a\n" + "\n" * 30 + "b\n"
    chunks = _chunk(text, path="x.go", window_lines=5, window_overlap=0)
    assert all(c.text.strip() for c in chunks)


def test_oversized_symbol_is_split_keeping_symbol_name():
    body = "\n".join(f"    value_{i} = {i}" for i in range(200))
    chunks = _chunk(f"def huge():\n{body}\n", max_chars=300)
    huge = [c for c in chunks if c.symbol_name == "huge"]
    assert len(huge) > 1
    assert all(len(c.text) <= 300 for c in huge)
    assert huge[0].def_line == 1 and all(c.def_line is None for c in huge[1:])
    assert len({c.id for c in huge}) == len(huge)


def test_single_line_longer_than_limit_is_hard_cut():
    chunks = _chunk("x = '" + "a" * 500 + "'\n", max_chars=100)
    assert len(chunks) >= 5
    assert all(len(c.text) <= 100 for c in chunks)
    assert all(c.start_line == c.end_line == 1 for c in chunks)


def test_tiny_module_chunks_such_as_import_lines_are_dropped():
    chunks = _chunk("import os\n\n\ndef f():\n    return 1\n")
    assert [c.symbol_name for c in chunks] == ["f"]
