from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass
from typing import Callable

from recall.chunk_spans import Span, leftover, module_spans

logger = logging.getLogger(__name__)

_ODD_NEWLINES = ("\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " ")
_CLOSERS_ONLY = re.compile(r"[\s})\];,]*")
_JS_FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}
_warned: set[str] = set()


@dataclass(frozen=True)
class _Described:
    qualname: str
    kind: str
    def_node: object


@dataclass(frozen=True)
class _Container:
    name: str
    header_name: str
    members: list
    full_rules: bool


@dataclass(frozen=True)
class _Spec:
    package: str
    wrappers: frozenset[str]
    comments: frozenset[str]
    attributes: frozenset[str]
    describe: Callable[..., _Described | None]
    container: Callable[..., _Container | None]


def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def _field(node, name: str) -> str:
    return _text(node.child_by_field_name(name))


def _first_ident(text: str) -> str:
    match = re.search(r"[A-Za-z_][A-Za-z0-9_]*", text)
    return match.group(0) if match else text


def _go_receiver_type(node) -> str:
    receiver = _field(node, "receiver")
    match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*\)\s*$", receiver)
    return match.group(1) if match else _first_ident(receiver)


def _go_describe(node, prefix: str, full: bool) -> _Described | None:
    if node.type == "function_declaration":
        return _Described(prefix + _field(node, "name"), "function", node)
    if node.type == "method_declaration":
        return _Described(f"{_go_receiver_type(node)}.{_field(node, 'name')}", "method", node)
    if node.type == "type_declaration":
        spec = next((c for c in node.named_children if c.type in ("type_spec", "type_alias")), None)
        if spec is not None:
            return _Described(prefix + _field(spec, "name"), "type", spec)
    return None


def _go_container(node) -> _Container | None:
    return None


def _js_describe(node, prefix: str, full: bool) -> _Described | None:
    kind = "method" if prefix else "function"
    if node.type in ("function_declaration", "generator_function_declaration"):
        return _Described(prefix + (_field(node, "name") or "default"), kind, node)
    if node.type == "method_definition":
        return _Described(prefix + _field(node, "name"), "method", node)
    if node.type in ("lexical_declaration", "variable_declaration") and not prefix:
        for declarator in node.named_children:
            value = declarator.child_by_field_name("value")
            if declarator.type == "variable_declarator" and value is not None and value.type in _JS_FUNCTION_VALUES:
                return _Described(_field(declarator, "name"), "function", node)
    return None


def _js_container(node) -> _Container | None:
    if node.type != "class_declaration":
        return None
    body = node.child_by_field_name("body")
    name = _field(node, "name") or "default"
    return _Container(name, name, list(body.named_children) if body is not None else [], False)


def _rust_describe(node, prefix: str, full: bool) -> _Described | None:
    if node.type == "function_item":
        return _Described(prefix + _field(node, "name"), "method" if prefix else "function", node)
    if full and node.type in ("struct_item", "enum_item", "union_item", "type_item"):
        return _Described(prefix + _field(node, "name"), "type", node)
    return None


def _rust_container(node) -> _Container | None:
    body = node.child_by_field_name("body")
    members = list(body.named_children) if body is not None else []
    if node.type == "impl_item":
        target = _first_ident(_field(node, "type"))
        trait = _first_ident(_field(node, "trait")) if node.child_by_field_name("trait") is not None else ""
        header = f"{target} (impl {trait})" if trait else target
        return _Container(target, header, members, False)
    if node.type == "trait_item":
        name = _field(node, "name")
        return _Container(name, name, members, False)
    if node.type == "mod_item" and body is not None:
        name = _field(node, "name")
        return _Container(name, name, members, True)
    return None


_SPECS: dict[str, _Spec] = {
    "go": _Spec("tree_sitter_go", frozenset(), frozenset({"comment"}), frozenset(), _go_describe, _go_container),
    "javascript": _Spec(
        "tree_sitter_javascript", frozenset({"export_statement"}), frozenset({"comment"}), frozenset(),
        _js_describe, _js_container,
    ),
    "rust": _Spec(
        "tree_sitter_rust", frozenset(), frozenset({"line_comment", "block_comment"}),
        frozenset({"attribute_item"}), _rust_describe, _rust_container,
    ),
}

_SUFFIXES = {
    ".go": "go",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".rs": "rust",
}


def supported_suffixes() -> set[str]:
    return set(_SUFFIXES)


def _parser(language: str):
    spec = _SPECS[language]
    try:
        from tree_sitter import Language, Parser

        module = importlib.import_module(spec.package)
    except ImportError:
        if language not in _warned:
            _warned.add(language)
            logger.warning(
                "tree-sitter support for %s is not installed — falling back to line windows "
                "(reinstall with: uv tool install --from \"recall[code] @ git+https://github.com/goriok/recall.git\" recall)", language,
            )
        return None
    return Parser(Language(module.language()))


def _end_line(node) -> int:
    row, column = node.end_point
    return row + 1 if column > 0 else row


class _Collector:
    def __init__(self, spec: _Spec, source_lines: list[bytes]) -> None:
        self.spec = spec
        self.source_lines = source_lines

    def _first_on_line(self, node) -> bool:
        row, column = node.start_point
        return self.source_lines[row][:column].strip() == b""

    def _extent(self, node) -> tuple[int, int]:
        start = node.start_point[0] + 1
        previous = node.prev_sibling
        while previous is not None and previous.type in self.spec.comments | self.spec.attributes:
            if _end_line(previous) < start - 1 or not self._first_on_line(previous):
                break
            start = previous.start_point[0] + 1
            previous = previous.prev_sibling
        return start, _end_line(node)

    def _unwrap(self, node):
        if node.type not in self.spec.wrappers:
            return node
        declaration = node.child_by_field_name("declaration")
        if declaration is not None:
            return declaration
        return next((c for c in node.named_children if c.type != "comment"), None)

    def collect(self, nodes, prefix: str, full: bool) -> list[Span]:
        spans: list[Span] = []
        for node in nodes:
            inner = self._unwrap(node)
            if inner is None:
                continue
            container = self.spec.container(inner) if (full or not prefix) else None
            if container is not None:
                spans.extend(self._container(node, inner, container, prefix))
                continue
            described = self.spec.describe(inner, prefix, full)
            if described is None:
                continue
            start, end = self._extent(node)
            spans.append(Span(start, end, described.def_node.start_point[0] + 1, described.qualname, described.kind))
        return spans

    def _container(self, node, inner, container: _Container, prefix: str) -> list[Span]:
        qualname = prefix + container.name
        start, end = self._extent(node)
        def_line = inner.start_point[0] + 1
        members = self.collect(container.members, f"{qualname}.", container.full_rules)
        if not members:
            return [Span(start, end, def_line, prefix + container.header_name, "class")]
        first = min(m.start for m in members)
        header = [Span(start, first - 1, def_line, prefix + container.header_name, "class")] if start < first else []
        lines = [b.decode("utf-8", errors="replace") for b in self.source_lines]
        rest = [
            Span(a, b, None, f"{qualname}.<resto>", "class_rest")
            for a, b in leftover(lines, start, end, header + members)
            if not _CLOSERS_ONLY.fullmatch("\n".join(lines[a - 1 : b]))
        ]
        return header + members + rest


def treesitter_spans(text: str, suffix: str) -> list[Span] | None:
    language = _SUFFIXES.get(suffix)
    if language is None:
        return None
    normalized = text.replace("\r\n", "\n")
    if any(ch in normalized for ch in _ODD_NEWLINES):
        logger.warning("unusual line separators — falling back to line windows")
        return None
    parser = _parser(language)
    if parser is None:
        return None

    data = normalized.encode("utf-8")
    root = parser.parse(data).root_node
    collector = _Collector(_SPECS[language], data.split(b"\n"))
    symbols = collector.collect(root.named_children, "", True)
    if not symbols and root.has_error:
        return None
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return sorted(symbols + module_spans(lines, symbols), key=lambda s: (s.start, s.end))
