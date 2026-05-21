from __future__ import annotations

import pytest
from pathlib import Path
from recall.config import Config, ProjectConfig, SourceConfig


def _make_source(root: str, subdirs: list[str], glob: str = "**/*.md", exclude: list[str] | None = None) -> SourceConfig:
    return SourceConfig(root=root, glob=glob, exclude=exclude or [])


def test_projects_from_source_returns_discovered_projects(tmp_path):
    """projects_from_source returns auto-discovered projects under the given source root."""
    root = tmp_path / "sources"
    for name in ["proj-a", "proj-b", "proj-c"]:
        d = root / name
        d.mkdir(parents=True)
        (d / "README.md").write_text("# doc")

    cfg = Config(
        sources=[
            SourceConfig(root=str(root), glob="**/*.md"),
            SourceConfig(root=str(tmp_path / "analysis"), glob="**/*.md"),
        ]
    )
    result = cfg.projects_from_source(str(root))

    names = {p.name for p in result}
    assert names == {"proj-a", "proj-b", "proj-c"}


def test_projects_from_source_filters_by_root(tmp_path):
    """Does not return projects from other source roots."""
    sources_root = tmp_path / "sources"
    analysis_root = tmp_path / "analysis"
    for name in ["s-proj"]:
        d = sources_root / name
        d.mkdir(parents=True)
        (d / "doc.md").write_text("x")
    for name in ["a-proj"]:
        d = analysis_root / name
        d.mkdir(parents=True)
        (d / "doc.md").write_text("x")

    cfg = Config(
        sources=[
            SourceConfig(root=str(sources_root), glob="**/*.md"),
            SourceConfig(root=str(analysis_root), glob="**/*.md"),
        ]
    )
    result = cfg.projects_from_source(str(sources_root))

    names = {p.name for p in result}
    assert names == {"s-proj"}
    assert "a-proj" not in names


def test_projects_from_source_resolves_tilde(tmp_path, monkeypatch):
    """~ in the source argument is resolved before comparing."""
    sources_root = tmp_path / "sources"
    proj_dir = sources_root / "myproj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "doc.md").write_text("x")

    monkeypatch.setenv("HOME", str(tmp_path))

    cfg = Config(sources=[SourceConfig(root=str(sources_root), glob="**/*.md")])

    result = cfg.projects_from_source("~/sources")

    assert len(result) == 1
    assert result[0].name == "myproj"


def test_projects_from_source_returns_empty_for_nonexistent_root(tmp_path):
    """No exception when the root directory doesn't exist."""
    cfg = Config(sources=[SourceConfig(root=str(tmp_path / "nonexistent"), glob="**/*.md")])
    result = cfg.projects_from_source(str(tmp_path / "nonexistent"))
    assert result == []
