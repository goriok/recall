from __future__ import annotations

import fnmatch
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


class DiscoveryError(Exception):
    pass


@dataclass
class DiscoveryResult:
    files: list[Path] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)


def expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end() :]
    return [p for option in match.group(1).split(",") for p in expand_braces(head + option + tail)]


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches_any(rel_posix: str, globs: list[str]) -> bool:
    return any(
        _glob_to_regex(expanded).match(rel_posix) for g in globs for expanded in expand_braces(g)
    )


def is_git_repo(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_ls_files(root: Path) -> list[str]:
    result = subprocess.run(
        [
            "git", "-C", str(root), "ls-files", "-z",
            "--cached", "--others", "--exclude-standard", "--deduplicate",
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    return [p.decode("utf-8", errors="surrogateescape") for p in result.stdout.split(b"\0") if p]


def _walk(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()]


def _is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return True


def _denied(rel: str, deny: list[str]) -> bool:
    low = rel.lower()
    name = low.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, d.lower()) or fnmatch.fnmatchcase(low, d.lower()) for d in deny)


def discover(
    root: Path,
    globs: list[str],
    path_exclude: list[str],
    deny: list[str],
    max_file_bytes: int,
) -> DiscoveryResult:
    root = root.expanduser()
    if not root.is_dir():
        raise DiscoveryError(f"{root} is not a directory")
    real_root = root.resolve()
    candidates = git_ls_files(root) if is_git_repo(root) else _walk(root)
    blocked = set(path_exclude)
    result = DiscoveryResult()

    for rel in sorted(candidates):
        if not matches_any(rel, globs):
            continue
        parts = rel.split("/")
        if any(part in blocked for part in parts):
            continue
        path = root / rel
        if _denied(rel, deny):
            result.skipped["denylist"] += 1
            continue
        if not path.is_file():
            continue
        target = path.resolve()
        if not target.is_relative_to(real_root):
            result.skipped["outside_root"] += 1
            continue
        if _denied(target.relative_to(real_root).as_posix(), deny):
            result.skipped["denylist"] += 1
            continue
        if path.stat().st_size > max_file_bytes:
            result.skipped["too_large"] += 1
            continue
        if _is_binary(path):
            result.skipped["binary"] += 1
            continue
        result.files.append(path)

    if not result.files:
        raise DiscoveryError(f"no files under {root} match {globs}")
    return result
