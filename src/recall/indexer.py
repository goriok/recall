from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from recall.chunker import chunk_markdown
from recall.code_chunker import chunk_code
from recall.config import Config, ProjectConfig
from recall.core.interfaces import EmbeddingProvider, Point, VectorStore
from recall.discovery import discover
from recall.graphify_adapter import GraphIndex, build_graph
from recall.meta import ModelMismatchError, check_model, read_meta, write_meta

logger = logging.getLogger(__name__)

FILE_BATCH = 20
POINT_WARNING = 15_000
REPORT_LIMIT = 200_000


@dataclass
class IndexReport:
    files: int = 0
    chunks: int = 0
    removed_files: int = 0
    skipped: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)
    graph: bool | None = None


@dataclass
class _Item:
    id: str
    embed_text: str
    payload: dict


def _point_id(chunk_id: str) -> int:
    return int(chunk_id, 16) % (2**63)


def _relative(path: Path, repo_root: Path, project_root: Path) -> str:
    resolved = path.resolve()
    for base in (repo_root, project_root):
        try:
            return resolved.relative_to(base.resolve()).as_posix()
        except ValueError:
            continue
    return path.name


def _markdown_items(text: str, path: Path, rel: str, project: ProjectConfig) -> list[_Item]:
    collection = project.collection
    repo_name = project.effective_repo_name
    chunks = chunk_markdown(
        text,
        source=str(path.resolve()),
        collection=collection,
        file_path=rel,
        repo_name=repo_name,
        max_chunk_chars=project.max_chunk_chars,
    )
    return [
        _Item(
            c.id,
            c.embed_text,
            {
                "text": c.text,
                "source": c.source,
                "file_path": rel,
                "repo_name": repo_name,
                "collection": collection,
                "heading": c.heading,
                "breadcrumb": c.breadcrumb,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "kind": "markdown",
            },
        )
        for c in chunks
    ]


def _code_items(text: str, rel: str, project: ProjectConfig, graph: GraphIndex | None) -> list[_Item]:
    repo_name = project.effective_repo_name
    chunks = chunk_code(
        text,
        file_path=rel,
        repo_name=repo_name,
        max_chars=project.max_chunk_chars,
        window_lines=project.window_lines,
        window_overlap=project.window_overlap,
        path_labels=project.path_labels,
    )
    items = []
    for c in chunks:
        payload = {
            "text": c.text,
            "file_path": rel,
            "repo_name": repo_name,
            "collection": project.collection,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "symbol_name": c.symbol_name,
            "kind": c.kind,
            "community": None,
            "community_name": "",
            "is_god_node": False,
            "related_symbols": [],
        }
        node_id = graph.find(rel, c.def_line, c.start_line, c.end_line, c.kind) if graph else None
        if node_id:
            info = graph.info(node_id, c.kind)
            payload.update(
                community=info.community_id,
                community_name=info.community_name,
                is_god_node=info.is_god_node,
                related_symbols=info.related_symbols,
            )
        items.append(_Item(c.id, c.embed_text, payload))
    return items


def _meta_extra(project: ProjectConfig, graph: GraphIndex | None) -> dict:
    extra: dict = {
        "repo_name": project.effective_repo_name,
        "kind": project.kind,
        "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if graph is not None:
        extra["report"] = graph.report[:REPORT_LIMIT]
        extra["god_nodes"] = graph.god_labels()
    return extra


def index_project(
    project: ProjectConfig,
    *,
    config: Config,
    vector_store: VectorStore,
    embedding_provider: EmbeddingProvider,
    recreate: bool = False,
    report: IndexReport | None = None,
) -> int:
    """Index a docs project or a code repo. Returns number of chunks indexed."""
    report = report if report is not None else IndexReport()
    root = project.resolved_path
    if not root.exists():
        return 0

    result = discover(root, project.effective_globs, project.path_exclude, project.deny, project.max_file_bytes)
    report.skipped.update(result.skipped)
    collection = project.collection
    repo_root = project.resolved_repo_root

    existed = vector_store.collection_exists(collection)
    if existed and not recreate:
        if read_meta(vector_store, collection) is None:
            recreate = True
            report.warnings.append(f"{collection}: legacy collection without model metadata — rebuilding it")
        else:
            check_model(vector_store, collection, embedding_provider.model_id, embedding_provider.dimensions)
    if recreate or not existed:
        vector_store.recreate_collection(collection, embedding_provider.dimensions)
        existed = False

    if project.max_chunk_chars > embedding_provider.max_input_chars:
        report.warnings.append(
            f"{collection}: max_chunk_chars={project.max_chunk_chars} exceeds the "
            f"{embedding_provider.max_input_chars}-char input limit of {embedding_provider.model_id}"
        )

    graph: GraphIndex | None = None
    if project.kind == "code" and project.graphify.enabled:
        graph = build_graph(root, project.effective_repo_name, project.graphify)
        report.graph = graph is not None

    relative = {path: _relative(path, repo_root, root) for path in result.files}
    removed = (
        vector_store.distinct_values(collection, "file_path") - set(relative.values()) if existed else set()
    )

    total = 0
    for i in range(0, len(result.files), FILE_BATCH):
        batch = result.files[i : i + FILE_BATCH]
        items: list[_Item] = []
        done: list[str] = []
        for path in batch:
            rel = relative[path]
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                report.skipped["unreadable"] += 1
                logger.warning("skipping %s: %s", rel, type(exc).__name__)
                continue
            if project.kind == "code" and path.suffix != ".md":
                items.extend(_code_items(text, rel, project, graph))
            else:
                items.extend(_markdown_items(text, path, rel, project))
            done.append(rel)
        report.files += len(done)
        vectors = embedding_provider.embed_batch([it.embed_text for it in items]) if items else []
        if done:
            vector_store.delete_where(collection, "file_path", done)
        points = [Point(id=_point_id(it.id), vector=v, payload=it.payload) for it, v in zip(items, vectors)]
        if points:
            vector_store.upsert(collection, points)
        total += len(points)

    if removed:
        vector_store.delete_where(collection, "file_path", sorted(removed))
        report.removed_files += len(removed)

    write_meta(
        vector_store, collection, embedding_provider.model_id, embedding_provider.dimensions,
        files=len(relative), **_meta_extra(project, graph),
    )
    count = vector_store.count(collection)
    if count > POINT_WARNING:
        report.warnings.append(
            f"{collection}: {count} points — the embedded Qdrant store degrades past ~20000; "
            f"use a Qdrant server for this collection"
        )
    report.chunks += total
    return total


__all__ = ["IndexReport", "ModelMismatchError", "index_project"]
