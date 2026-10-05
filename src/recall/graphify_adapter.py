from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from recall.config import GraphifyConfig

logger = logging.getLogger(__name__)

_LOCATION = re.compile(r"^L(\d+)$")
_SYMBOL_RELATIONS = {"calls", "inherits", "imports"}
_MODULE_RELATIONS = {"calls", "inherits", "imports", "imports_from"}

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass
class GraphInfo:
    community_id: int | None = None
    community_name: str = ""
    is_god_node: bool = False
    related_symbols: list[str] = field(default_factory=list)


@dataclass
class GraphIndex:
    god_ids: set[str] = field(default_factory=set)
    report: str = ""
    nodes: dict[str, dict] = field(default_factory=dict)
    by_location: dict[tuple[str, int], str] = field(default_factory=dict)
    by_file: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    file_nodes: dict[str, str] = field(default_factory=dict)
    qualified: dict[str, str] = field(default_factory=dict)
    neighbors: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    related_max: int = 10

    def find(self, file_path: str, def_line: int | None, start_line: int, end_line: int, kind: str) -> str | None:
        if kind == "window":
            return None
        if kind == "module":
            return self.file_nodes.get(file_path)
        if def_line is not None and (file_path, def_line) in self.by_location:
            return self.by_location[(file_path, def_line)]
        candidates = [
            (line, node_id)
            for line, node_id in self.by_file.get(file_path, [])
            if start_line <= line <= end_line and line > 1
        ]
        return min(candidates)[1] if candidates else None

    def god_labels(self) -> list[str]:
        return sorted(self.qualified[g] for g in self.god_ids if g in self.qualified)

    def info(self, node_id: str, kind: str) -> GraphInfo:
        node = self.nodes[node_id]
        relations = _MODULE_RELATIONS if kind == "module" else _SYMBOL_RELATIONS
        names: list[str] = []
        for relation in sorted(relations):
            for other in sorted(self.neighbors.get(node_id, {}).get(relation, set())):
                name = self.qualified.get(other)
                if name and name not in names:
                    names.append(name)
        return GraphInfo(
            community_id=node.get("community"),
            community_name=str(node.get("community_name") or ""),
            is_god_node=node_id in self.god_ids,
            related_symbols=names[: self.related_max],
        )


def cache_dir(repo_name: str) -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "recall" / "graphify" / repo_name


def _line(location: object) -> int | None:
    match = _LOCATION.match(str(location or ""))
    return int(match.group(1)) if match else None


def _relative(source_file: str, root: Path) -> str:
    if not source_file:
        return ""
    path = Path(source_file)
    if path.is_absolute():
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return ""
    return path.as_posix().removeprefix("./")


def _qualified_label(node: dict) -> str:
    return str(node.get("label", "")).removesuffix("()").removeprefix(".")


def parse_graph(graph: dict, god_ids: set[str], report: str, root: Path, related_max: int = 10) -> GraphIndex:
    index = GraphIndex(god_ids=god_ids, report=report, related_max=related_max)
    for node in graph.get("nodes", []):
        file_path = _relative(node.get("source_file") or "", root)
        if not file_path:
            continue
        node = {**node, "source_file": file_path}
        node_id = node["id"]
        index.nodes[node_id] = node
        index.qualified[node_id] = _qualified_label(node)
        line = _line(node.get("source_location"))
        if line is None:
            continue
        index.by_location[(file_path, line)] = node_id
        index.by_file.setdefault(file_path, []).append((line, node_id))
        if line == 1 and node.get("label") == Path(file_path).name:
            index.file_nodes[file_path] = node_id

    for edge in graph.get("links", []):
        source, target, relation = edge.get("source"), edge.get("target"), edge.get("relation")
        if source not in index.nodes or target not in index.nodes:
            continue
        if relation == "method":
            owner = _qualified_label(index.nodes[source])
            index.qualified[target] = f"{owner}.{_qualified_label(index.nodes[target])}"
            continue
        if edge.get("confidence") != "EXTRACTED":
            continue
        index.neighbors.setdefault(source, {}).setdefault(relation, set()).add(target)
        index.neighbors.setdefault(target, {}).setdefault(relation, set()).add(source)
    return index


def build_graph(
    root: Path,
    repo_name: str,
    cfg: GraphifyConfig,
    runner: Runner = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> GraphIndex | None:
    if not which("graphify"):
        logger.warning("graphify not found on PATH — indexing %s without graph metadata", repo_name)
        return None
    out = cache_dir(repo_name)
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GRAPHIFY_OUT": str(out)}
    root = root.expanduser().resolve()
    try:
        runner(
            ["graphify", "update", str(root), "--force"],
            env=env, cwd=root, timeout=cfg.timeout_seconds, check=True, capture_output=True,
        )
        god = runner(
            ["graphify", "god-nodes", "--top", str(cfg.god_nodes_top), "--json"],
            env=env, cwd=root, timeout=cfg.timeout_seconds, check=True, capture_output=True, text=True,
        )
        graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
        god_ids = {entry["id"] for entry in json.loads(god.stdout)}
        report_path = out / "GRAPH_REPORT.md"
        report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        logger.warning("graphify failed for %s (%s) — indexing without graph metadata", repo_name, type(exc).__name__)
        return None
    return parse_graph(graph, god_ids, report, root, cfg.related_max)
