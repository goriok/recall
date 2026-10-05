from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

_HEADING = re.compile(r"^(#{1,6}) +(.*\S)\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SPLIT_LEVEL = 2


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    collection: str
    heading: str
    file_path: str = ""
    breadcrumb: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    embed_text: str = ""


def _make_id(source: str, heading: str, index: int) -> str:
    key = f"{source}::{heading}::{index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _stable_id(repo_name: str, file_path: str, breadcrumb: list[str], k: int) -> str:
    key = f"{repo_name}::{file_path}::{' > '.join(breadcrumb)}::{k}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass
class _Heading:
    line: int
    level: int
    text: str
    breadcrumb: list[str]


def _scan_headings(lines: list[str]) -> list[_Heading]:
    headings: list[_Heading] = []
    stack: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    for number, line in enumerate(lines, start=1):
        fence_match = _FENCE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1] and not fence_match.group(2).strip():
                fence = None
            continue
        if fence is not None:
            continue
        heading_match = _HEADING.match(line)
        if not heading_match:
            continue
        level = len(heading_match.group(1))
        text = heading_match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
        headings.append(_Heading(number, level, text, [t for _, t in stack]))
    return headings


def _trim(lines: list[str], start: int, end: int) -> tuple[int, int] | None:
    while start <= end and not lines[start - 1].strip():
        start += 1
    while end >= start and not lines[end - 1].strip():
        end -= 1
    return (start, end) if start <= end else None


@dataclass
class _Piece:
    start: int
    end: int
    breadcrumb: list[str]
    heading: str
    text: str | None = None


def _has_body(lines: list[str], start: int, end: int, headed: bool) -> bool:
    first = start + 1 if headed else start
    return any(lines[n - 1].strip() for n in range(first, end + 1))


def _plain_split(lines: list[str], start: int, end: int, max_chars: int) -> list[tuple[int, int, str | None]]:
    paragraphs: list[tuple[int, int]] = []
    n = start
    while n <= end:
        if not lines[n - 1].strip():
            n += 1
            continue
        first = n
        while n <= end and lines[n - 1].strip():
            n += 1
        paragraphs.append((first, n - 1))

    pieces: list[tuple[int, int, str | None]] = []
    current: tuple[int, int] | None = None

    def size(span: tuple[int, int]) -> int:
        return len("\n".join(lines[span[0] - 1 : span[1]]))

    def flush() -> None:
        nonlocal current
        if current is not None:
            pieces.append((current[0], current[1], None))
            current = None

    for first, last in paragraphs:
        if size((first, last)) > max_chars:
            flush()
            for line_no in range(first, last + 1):
                line = lines[line_no - 1]
                if len(line) > max_chars:
                    flush()
                    for offset in range(0, len(line), max_chars):
                        pieces.append((line_no, line_no, line[offset : offset + max_chars]))
                    continue
                candidate = (current[0], line_no) if current else (line_no, line_no)
                if current and size(candidate) > max_chars:
                    flush()
                    candidate = (line_no, line_no)
                current = candidate
            flush()
            continue
        candidate = (current[0], last) if current else (first, last)
        if current and size(candidate) > max_chars:
            flush()
            candidate = (first, last)
        current = candidate
    flush()
    return pieces


def _split_segment(
    lines: list[str],
    headings: list[_Heading],
    start: int,
    end: int,
    level: int,
    breadcrumb: list[str],
    heading: str,
    max_chars: int,
) -> list[_Piece]:
    span = _trim(lines, start, end)
    if span is None:
        return []
    start, end = span
    text = "\n".join(lines[start - 1 : end])
    if max_chars <= 0 or len(text) <= max_chars:
        return [_Piece(start, end, breadcrumb, heading)]

    inner = [h for h in headings if start < h.line <= end and h.level > level]
    if inner:
        deepest = min(h.level for h in inner)
        cuts = [h for h in inner if h.level == deepest]
        bounds = [start] + [h.line for h in cuts] + [end + 1]
        pieces: list[_Piece] = []
        for i in range(len(bounds) - 1):
            seg_start, seg_end = bounds[i], bounds[i + 1] - 1
            if i == 0:
                if not _has_body(lines, seg_start, seg_end, level > 0):
                    continue
                pieces.extend(
                    _split_segment(lines, headings, seg_start, seg_end, level, breadcrumb, heading, max_chars)
                )
                continue
            cut = cuts[i - 1]
            if not _has_body(lines, seg_start, seg_end, True):
                continue
            pieces.extend(
                _split_segment(lines, headings, seg_start, seg_end, cut.level, cut.breadcrumb, cut.text, max_chars)
            )
        return pieces

    return [
        _Piece(s, e, breadcrumb, heading, text)
        for s, e, text in _plain_split(lines, start, end, max_chars)
    ]


def chunk_markdown(
    text: str,
    *,
    source: str,
    collection: str,
    file_path: str | None = None,
    repo_name: str = "",
    max_chunk_chars: int = 0,
) -> list[Chunk]:
    """Split markdown into chunks on h1/h2 boundaries, ignoring headings inside fenced code.

    Each chunk records the 1-indexed line span it covers and its heading breadcrumb.
    Sections that only have a heading are skipped. With max_chunk_chars > 0, oversized
    sections are split at deeper headings, then blank lines, then a hard character cut.
    """
    lines = text.splitlines()
    headings = _scan_headings(lines)
    splitters = [h for h in headings if h.level <= _SPLIT_LEVEL]

    bounds: list[tuple[int, _Heading | None]] = []
    if not splitters or splitters[0].line > 1:
        bounds.append((1, None))
    bounds.extend((h.line, h) for h in splitters)

    pieces: list[_Piece] = []
    for i, (seg_start, head) in enumerate(bounds):
        seg_end = (bounds[i + 1][0] - 1) if i + 1 < len(bounds) else len(lines)
        if not _has_body(lines, seg_start, seg_end, head is not None):
            continue
        if head is None:
            pieces.extend(_split_segment(lines, headings, seg_start, seg_end, 0, [], "", max_chunk_chars))
        else:
            pieces.extend(
                _split_segment(lines, headings, seg_start, seg_end, head.level, head.breadcrumb, head.text, max_chunk_chars)
            )

    chunks: list[Chunk] = []
    seen: dict[tuple[str, ...], int] = {}
    for index, piece in enumerate(pieces):
        body = piece.text if piece.text is not None else "\n".join(lines[piece.start - 1 : piece.end])
        crumb_key = tuple(piece.breadcrumb)
        k = seen.get(crumb_key, 0)
        seen[crumb_key] = k + 1
        if file_path is not None:
            chunk_id = _stable_id(repo_name, file_path, piece.breadcrumb, k)
            embed_text = f"# {' > '.join(piece.breadcrumb)}\n\n{body}" if piece.breadcrumb else body
        else:
            chunk_id = _make_id(source, piece.heading, index)
            embed_text = body
        chunks.append(
            Chunk(
                id=chunk_id,
                text=body,
                source=source,
                collection=collection,
                heading=piece.heading,
                file_path=file_path or "",
                breadcrumb=list(piece.breadcrumb),
                start_line=piece.start,
                end_line=piece.end,
                embed_text=embed_text,
            )
        )
    return chunks
