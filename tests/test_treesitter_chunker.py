from __future__ import annotations

import builtins

import pytest

from recall import treesitter_chunker
from recall.code_chunker import chunk_code

GO = '''package main

import (
	"fmt"
	"net/http"
)

// Server handles requests.
type Server struct {
	Addr string
}

type Handler interface {
	Serve(w http.ResponseWriter)
}

const Version = "1.0.0-a-long-constant-value-so-it-survives-the-filter"

// Start launches the server.
func (s *Server) Start() error {
	fmt.Println("starting", s.Addr)
	return nil
}

func (Server) Stop() {}

func (s *Box[T]) Get() T { var zero T; return zero }

func NewServer(addr string) *Server {
	return &Server{Addr: addr}
}
'''

JS = '''import fs from "fs";

/**
 * Adds numbers.
 */
export function add(a, b) {
  return a + b;
}

const multiply = (a, b) => {
  return a * b;
};

const plain = 42;

export default class Calculator {
  constructor(base) {
    this.base = base;
  }

  /** run it */
  run(x) {
    return add(this.base, x);
  }

  static create() {
    return new Calculator(0);
  }
}

module.exports = { add, multiply, Calculator, somethingElseThatIsLongEnough: true };
'''

RUST = '''use std::collections::HashMap;

/// A cache of values.
#[derive(Debug, Clone)]
pub struct Cache {
    data: HashMap<String, String>,
}

pub trait Store {
    fn get(&self, key: &str) -> Option<String>;
    fn put(&mut self, key: String, value: String) {
        let _ = (key, value);
    }
}

pub trait Marker {
    fn id(&self) -> u32;
}

impl Cache {
    pub fn new() -> Self {
        Cache { data: HashMap::new() }
    }

    /// Looks a key up.
    pub fn lookup(&self, key: &str) -> Option<&String> {
        self.data.get(key)
    }
}

impl<T> Store for Cache<T> {
    fn get(&self, key: &str) -> Option<String> {
        self.data.get(key).cloned()
    }
}

pub fn helper(x: i32) -> i32 {
    x + 1
}

mod inner {
    pub struct Deep;
    pub fn deep() -> i32 { 1 }
}
'''


def _chunks(source, path, **kwargs):
    return chunk_code(source, file_path=path, repo_name="repo", max_chars=4000, **kwargs)


def _by(chunks):
    out = {}
    for c in chunks:
        out.setdefault(c.symbol_name, c)
    return out


def _text_matches_lines(source, chunks):
    lines = source.splitlines()
    for c in chunks:
        assert c.text == "\n".join(lines[c.start_line - 1 : c.end_line])


def test_go_symbols_lines_and_receivers():
    chunks = _chunks(GO, "svc/main.go")
    by = _by(chunks)

    assert {"Server", "Handler", "Server.Start", "Server.Stop", "Box.Get", "NewServer"} <= set(by)
    server = by["Server"]
    assert server.kind == "type" and server.text.startswith("// Server handles requests.")
    assert server.def_line == 9
    start = by["Server.Start"]
    assert start.kind == "method" and start.start_line == 19 and start.def_line == 20
    assert by["NewServer"].kind == "function"
    _text_matches_lines(GO, chunks)


def test_go_package_and_imports_are_not_chunks_but_long_constants_are():
    chunks = _chunks(GO, "main.go")
    modules = [c for c in chunks if c.kind == "module"]
    assert [m.text.split(" ")[0] for m in modules] == ["const"]


def test_javascript_functions_arrows_and_classes():
    chunks = _chunks(JS, "web/app.js")
    by = _by(chunks)

    assert {"add", "multiply", "Calculator", "Calculator.constructor", "Calculator.run", "Calculator.create"} <= set(by)
    add = by["add"]
    assert add.text.startswith("/**") and add.def_line == 6 and add.kind == "function"
    assert by["multiply"].kind == "function" and by["multiply"].def_line == 10
    run = by["Calculator.run"]
    assert run.kind == "method" and run.text.strip().startswith("/** run it */")
    assert "plain" not in by
    _text_matches_lines(JS, chunks)


def test_javascript_module_exports_stay_in_module_chunk():
    chunks = _chunks(JS, "app.js")
    assert any(c.kind == "module" and "module.exports" in c.text for c in chunks)


def test_javascript_extensions_share_the_grammar():
    for ext in (".mjs", ".cjs", ".jsx"):
        assert "add" in _by(_chunks(JS, f"x{ext}"))


def test_rust_items_include_attributes_and_doc_comments():
    chunks = _chunks(RUST, "src/lib.rs")
    by = _by(chunks)

    cache = by["Cache"]
    assert cache.kind == "type"
    assert cache.text.startswith("/// A cache of values.\n#[derive(Debug, Clone)]")
    assert cache.start_line == 3 and cache.def_line == 5
    lookup = by["Cache.lookup"]
    assert lookup.text.strip().startswith("/// Looks a key up.") and lookup.def_line == 26
    _text_matches_lines(RUST, chunks)


def test_rust_impl_trait_and_mod_naming():
    chunks = _chunks(RUST, "lib.rs")
    symbols = [c.symbol_name for c in chunks]

    assert "Cache.new" in symbols and "Cache.lookup" in symbols
    assert "Cache.get" in symbols
    assert "Cache (impl Store)" in symbols
    assert "Store.put" in symbols
    assert "helper" in symbols
    assert "inner.deep" in symbols and "inner.Deep" in symbols


def test_rust_trait_with_only_signatures_is_one_chunk():
    marker = [c for c in _chunks(RUST, "lib.rs") if c.symbol_name == "Marker"]
    assert len(marker) == 1 and "fn id" in marker[0].text


def test_container_closing_braces_do_not_become_chunks():
    for source, path in ((JS, "a.js"), (RUST, "a.rs")):
        for chunk in _chunks(source, path):
            assert chunk.text.strip("\n\t ;,})]") != "", chunk


def test_trailing_comment_of_previous_line_is_not_swallowed_into_next_symbol():
    source = "x := 1 // note about x\nfunc A() {\n\treturn\n}\n" * 0 + (
        "package p\n\nvar x = 1 // note about x\nfunc A() int {\n\treturn 1\n}\n"
    )
    a = _by(_chunks(source, "p.go"))["A"]
    assert a.start_line == 4 and "note about x" not in a.text


def test_comment_separated_by_blank_line_is_not_part_of_the_symbol():
    source = "package p\n\n// floating comment\n\nfunc A() int {\n\treturn 1\n}\n"
    a = _by(_chunks(source, "p.go"))["A"]
    assert a.start_line == 5


def test_ids_are_stable_when_lines_are_inserted_above():
    before = _by(_chunks(GO, "main.go"))
    after = _by(_chunks("// header\n// more\n" + GO, "main.go"))
    for name in ("Server.Start", "NewServer", "Server"):
        assert before[name].id == after[name].id
        assert before[name].start_line != after[name].start_line


def test_duplicate_names_get_distinct_ids():
    source = "package p\n\nfunc A() int {\n\treturn 1\n}\n\nfunc A() int {\n\treturn 2\n}\n"
    chunks = [c for c in _chunks(source, "p.go") if c.symbol_name == "A"]
    assert len(chunks) == 2 and chunks[0].id != chunks[1].id


def test_syntax_errors_still_chunk_what_parses():
    source = "package p\n\nfunc Good() int {\n\treturn 1\n}\n\nfunc Bad( {\n"
    assert "Good" in _by(_chunks(source, "p.go"))


def test_garbage_without_symbols_falls_back_to_windows():
    chunks = _chunks("}{ not really go at all ((( \n" * 8, "junk.go", window_lines=4, window_overlap=1)
    assert chunks and all(c.kind == "window" for c in chunks)


def test_crlf_sources_chunk_like_lf():
    lf = _by(_chunks(RUST, "lib.rs"))
    crlf = _by(_chunks(RUST.replace("\n", "\r\n"), "lib.rs"))
    assert {k: (v.start_line, v.end_line) for k, v in lf.items()} == {
        k: (v.start_line, v.end_line) for k, v in crlf.items()
    }


def test_unusual_line_separators_fall_back_to_windows():
    source = "package p\x0c\n\nfunc A() int {\n\treturn 1\n}\n"
    assert all(c.kind == "window" for c in _chunks(source, "p.go"))


def test_unsupported_extension_uses_windows():
    assert all(c.kind == "window" for c in _chunks("a\nb\nc\n", "notes.txt"))
    assert treesitter_chunker.treesitter_spans("x", ".java") is None


def test_missing_grammar_falls_back_with_a_single_warning(monkeypatch, caplog):
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("tree_sitter"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    monkeypatch.setattr(treesitter_chunker, "_warned", set())
    monkeypatch.setattr(treesitter_chunker.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))

    first = _chunks(GO, "main.go", window_lines=10)
    second = _chunks(GO, "other.go", window_lines=10)

    assert all(c.kind == "window" for c in first + second)
    assert caplog.text.count("not installed") == 1
    assert "recall" in caplog.text


def test_oversized_symbol_is_split_like_python():
    body = "\n".join(f"\tv{i} := {i}" for i in range(300))
    chunks = chunk_code(f"package p\n\nfunc Huge() {{\n{body}\n}}\n", file_path="p.go", repo_name="r", max_chars=300)
    huge = [c for c in chunks if c.symbol_name == "Huge"]
    assert len(huge) > 1 and all(len(c.text) <= 300 for c in huge)
    assert huge[0].def_line == 3 and all(c.def_line is None for c in huge[1:])


def test_supported_suffixes_cover_the_three_languages():
    assert {".go", ".js", ".mjs", ".cjs", ".jsx", ".rs"} <= treesitter_chunker.supported_suffixes()


@pytest.mark.parametrize("path", ["a.go", "a.js", "a.rs"])
def test_empty_or_comment_only_files_do_not_crash(path):
    assert chunk_code("\n\n", file_path=path, repo_name="r", max_chars=100) == []
    chunk_code("// only a comment\n", file_path=path, repo_name="r", max_chars=100)
