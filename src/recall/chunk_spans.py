from __future__ import annotations

from dataclasses import dataclass

MIN_MODULE_CHARS = 60


@dataclass
class Span:
    start: int
    end: int
    def_line: int | None
    symbol: str
    kind: str
    text: str | None = None


def leftover(lines: list[str], start: int, end: int, covered: list[Span]) -> list[tuple[int, int]]:
    taken = sorted((s.start, s.end) for s in covered)
    gaps: list[tuple[int, int]] = []
    cursor = start
    for s, e in taken:
        if s > cursor:
            gaps.append((cursor, s - 1))
        cursor = max(cursor, e + 1)
    if cursor <= end:
        gaps.append((cursor, end))
    trimmed = []
    for a, b in gaps:
        while a <= b and not lines[a - 1].strip():
            a += 1
        while b >= a and not lines[b - 1].strip():
            b -= 1
        if a <= b:
            trimmed.append((a, b))
    return trimmed


def module_spans(lines: list[str], symbols: list[Span]) -> list[Span]:
    spans = [Span(a, b, None, "<module>", "module") for a, b in leftover(lines, 1, len(lines), symbols)]
    return [s for s in spans if len("\n".join(lines[s.start - 1 : s.end]).strip()) >= MIN_MODULE_CHARS]
