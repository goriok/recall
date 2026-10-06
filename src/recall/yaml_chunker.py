from __future__ import annotations

import re

from recall.chunk_spans import MIN_MODULE_CHARS, Span, leftover

KIND = "yaml_key"
PACK_CHARS = 800
MAX_DEPTH = 4
_KEY = re.compile(r"""^( *)([^\s#\-\[\]{}&*!|>'"%@`][^:]*|"[^"]*"|'[^']*'):(?:\s|$)""")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _size(lines: list[str], start: int, end: int) -> int:
    return len("\n".join(lines[start - 1 : end]))


def _siblings(lines: list[str], start: int, end: int, indent: int) -> list[tuple[int, int, str]]:
    keys: list[tuple[int, str]] = []
    for number in range(start, end + 1):
        line = lines[number - 1]
        if line.startswith("---"):
            keys.append((number, ""))
            continue
        match = _KEY.match(line)
        if match and len(match.group(1)) == indent:
            keys.append((number, match.group(2).strip().strip("\"'")))
    blocks: list[tuple[int, int, str]] = []
    for i, (number, name) in enumerate(keys):
        if not name:
            continue
        first = number
        floor = keys[i - 1][0] + 1 if i else start
        while first - 1 >= floor and _is_comment(lines[first - 2]) and _indent(lines[first - 2]) == indent:
            first -= 1
        nxt = keys[i + 1][0] if i + 1 < len(keys) else end + 1
        while nxt - 1 > number and _is_comment(lines[nxt - 2]) and _indent(lines[nxt - 2]) == indent and keys[i + 1 : i + 2] and keys[i + 1][1]:
            nxt -= 1
        last = nxt - 1
        while last > number and not lines[last - 1].strip():
            last -= 1
        blocks.append((first, last, name))
    return blocks


def _child_indent(lines: list[str], key_line: int, end: int, indent: int) -> int | None:
    for number in range(key_line + 1, end + 1):
        line = lines[number - 1]
        if not line.strip() or _is_comment(line):
            continue
        match = _KEY.match(line)
        return len(match.group(1)) if match and len(match.group(1)) > indent else None
    return None


def _key_line(lines: list[str], first: int, indent: int) -> int:
    while _is_comment(lines[first - 1]) or not lines[first - 1].strip():
        first += 1
    return first


def _pack(lines: list[str], items: list[Span], limit: int) -> list[Span]:
    packed: list[Span] = []
    group: list[Span] = []

    def flush() -> None:
        if not group:
            return
        names = [s.symbol.rsplit(".", 1)[-1] for s in group]
        prefix = group[0].symbol[: len(group[0].symbol) - len(names[0])]
        symbol = group[0].symbol if len(group) == 1 else f"{prefix}{names[0]}..{names[-1]}"
        packed.append(Span(group[0].start, group[-1].end, group[0].def_line, symbol, KIND))
        group.clear()

    for span in items:
        if group and (
            _size(lines, group[0].start, span.end) > limit
            or any(l.startswith("---") for l in lines[group[-1].end : span.start - 1])
        ):
            flush()
        group.append(span)
    flush()
    return packed


def _split(lines: list[str], start: int, end: int, indent: int, prefix: str, max_chars: int, depth: int) -> list[Span]:
    out: list[Span] = []
    run: list[Span] = []
    limit = min(PACK_CHARS, max_chars)
    for first, last, name in _siblings(lines, start, end, indent):
        symbol = f"{prefix}{name}"
        key_line = _key_line(lines, first, indent)
        child = _child_indent(lines, key_line, last, indent) if depth < MAX_DEPTH else None
        if _size(lines, first, last) > max_chars and child is not None:
            out.extend(_pack(lines, run, limit))
            run = []
            children = _siblings(lines, key_line + 1, last, child)
            head_end = (children[0][0] - 1) if children else last
            while head_end > first and not lines[head_end - 1].strip():
                head_end -= 1
            out.append(Span(first, head_end, key_line, symbol, KIND))
            out.extend(_split(lines, key_line + 1, last, child, f"{symbol}.", max_chars, depth + 1))
        else:
            span = Span(first, last, key_line, symbol, KIND)
            if _size(lines, first, last) > limit:
                out.extend(_pack(lines, run, limit))
                run = []
                out.append(span)
            else:
                run.append(span)
    out.extend(_pack(lines, run, limit))
    return out


def yaml_spans(text: str, max_chars: int) -> list[Span] | None:
    if "{{" in text:
        return None
    lines = text.splitlines()
    spans = _split(lines, 1, len(lines), 0, "", max_chars, 0)
    if not spans:
        return None
    rest = [
        Span(a, b, None, "<resto>", KIND)
        for a, b in leftover(lines, 1, len(lines), spans)
        if _size(lines, a, b) >= MIN_MODULE_CHARS and not lines[a - 1].startswith("---")
    ]
    return sorted(spans + rest, key=lambda s: (s.start, s.end))
