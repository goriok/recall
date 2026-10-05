from __future__ import annotations

import ast
import hashlib
import logging
import os
from dataclasses import dataclass

from recall.chunk_spans import Span as _Span, leftover as _leftover, module_spans as _module_spans
from recall.treesitter_chunker import treesitter_spans

logger = logging.getLogger(__name__)

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPOUND = (ast.If, ast.Try, ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)


@dataclass
class CodeChunk:
    id: str
    text: str
    embed_text: str
    file_path: str
    start_line: int
    end_line: int
    def_line: int | None
    symbol_name: str
    kind: str


def _hash(*parts: object) -> str:
    return hashlib.sha256("::".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _node_start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([d.lineno for d in decorators] + [node.lineno])


def _blocks(node: ast.AST) -> list[list[ast.stmt]]:
    blocks = [getattr(node, "body", [])]
    blocks.append(getattr(node, "orelse", []))
    blocks.append(getattr(node, "finalbody", []))
    for handler in getattr(node, "handlers", []):
        blocks.append(handler.body)
    return [b for b in blocks if b]


def _collect(body: list[ast.stmt], prefix: str, lines: list[str]) -> list[_Span]:
    spans: list[_Span] = []
    for node in body:
        if isinstance(node, _FUNCTIONS):
            kind = "method" if prefix else "function"
            spans.append(_Span(_node_start(node), node.end_lineno, node.lineno, f"{prefix}{node.name}", kind))
        elif isinstance(node, ast.ClassDef):
            spans.extend(_class_spans(node, prefix, lines))
        elif isinstance(node, _COMPOUND):
            for block in _blocks(node):
                spans.extend(_collect(block, prefix, lines))
    return spans


def _class_spans(node: ast.ClassDef, prefix: str, lines: list[str]) -> list[_Span]:
    qualname = f"{prefix}{node.name}"
    start, end = _node_start(node), node.end_lineno
    members = _collect(node.body, f"{qualname}.", lines)
    if not members:
        return [_Span(start, end, node.lineno, qualname, "class")]
    first_member = min(m.start for m in members)
    header = [_Span(start, first_member - 1, node.lineno, qualname, "class")] if start < first_member else []
    rest = [
        _Span(a, b, None, f"{qualname}.<resto>", "class_rest")
        for a, b in _leftover(lines, start, end, header + members)
    ]
    return header + members + rest


def _chunk_python(text: str) -> list[_Span]:
    tree = ast.parse(text)
    lines = text.splitlines()
    symbols = _collect(tree.body, "", lines)
    return sorted(symbols + _module_spans(lines, symbols), key=lambda sp: (sp.start, sp.end))


def _window_spans(lines: list[str], window_lines: int, overlap: int) -> list[_Span]:
    step = max(window_lines - overlap, 1)
    spans = []
    start = 1
    while start <= len(lines):
        end = min(start + window_lines - 1, len(lines))
        if any(line.strip() for line in lines[start - 1 : end]):
            spans.append(_Span(start, end, None, "", "window"))
        if end == len(lines):
            break
        start += step
    return spans


def _fit(lines: list[str], span: _Span, max_chars: int) -> list[_Span]:
    text = "\n".join(lines[span.start - 1 : span.end])
    if max_chars <= 0 or len(text) <= max_chars:
        return [span]
    pieces: list[_Span] = []
    current_start = span.start
    size = 0
    for number in range(span.start, span.end + 1):
        line = lines[number - 1]
        if len(line) > max_chars:
            if number > current_start and size:
                pieces.append(_Span(current_start, number - 1, None, span.symbol, span.kind))
            for offset in range(0, len(line), max_chars):
                pieces.append(_Span(number, number, None, span.symbol, span.kind, line[offset : offset + max_chars]))
            current_start, size = number + 1, 0
            continue
        if size and size + len(line) + 1 > max_chars:
            pieces.append(_Span(current_start, number - 1, None, span.symbol, span.kind))
            current_start, size = number, 0
        size += len(line) + 1
    if current_start <= span.end and size:
        pieces.append(_Span(current_start, span.end, None, span.symbol, span.kind))
    if pieces:
        pieces[0].def_line = span.def_line
    return pieces


def chunk_code(
    text: str,
    *,
    file_path: str,
    repo_name: str,
    max_chars: int,
    window_lines: int = 60,
    window_overlap: int = 10,
) -> list[CodeChunk]:
    lines = text.splitlines()
    if not any(line.strip() for line in lines):
        return []

    spans: list[_Span] | None = None
    if file_path.endswith(".py"):
        try:
            spans = _chunk_python(text)
        except (SyntaxError, ValueError):
            logger.warning("could not parse %s as Python — falling back to line windows", file_path)
    else:
        spans = treesitter_spans(text, os.path.splitext(file_path)[1].lower())
    if spans is None:
        spans = _window_spans(lines, window_lines, window_overlap)

    chunks: list[CodeChunk] = []
    seen: dict[tuple[str, str], int] = {}
    for span in spans:
        for piece in _fit(lines, span, max_chars):
            body = piece.text if piece.text is not None else "\n".join(lines[piece.start - 1 : piece.end])
            if piece.kind == "window":
                chunk_id = _hash(repo_name, file_path, "window", piece.start, len(chunks))
            else:
                key = (piece.symbol, piece.kind)
                k = seen.get(key, 0)
                seen[key] = k + 1
                chunk_id = _hash(repo_name, file_path, piece.symbol, k)
            label = f" {piece.symbol}" if piece.symbol else ""
            header = f"# {file_path}:{piece.start}-{piece.end}{label}"
            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    text=body,
                    embed_text=f"{header}\n\n{body}",
                    file_path=file_path,
                    start_line=piece.start,
                    end_line=piece.end,
                    def_line=piece.def_line,
                    symbol_name=piece.symbol,
                    kind=piece.kind,
                )
            )
    return chunks
