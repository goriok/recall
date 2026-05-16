import pytest
from pathlib import Path
from recall.config import load_config, SourceConfig, Config


def test_load_config_parses_sources(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text(
        '[[sources]]\nroot = "~/sources"\nglob = "**/*.md"\nexclude = ["node_modules"]\n'
    )
    cfg = load_config(toml)
    assert len(cfg.sources) == 1
    assert cfg.sources[0].root == "~/sources"
    assert cfg.sources[0].glob == "**/*.md"
    assert "node_modules" in cfg.sources[0].exclude


def test_source_config_defaults(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text('[[sources]]\nroot = "~/sources"\n')
    cfg = load_config(toml)
    assert cfg.sources[0].glob == "**/*.md"
    assert cfg.sources[0].exclude == []


def test_discover_projects_returns_one_per_subdir(tmp_path):
    (tmp_path / "proj-a").mkdir()
    (tmp_path / "proj-b").mkdir()
    (tmp_path / "proj-a" / "doc.md").write_text("# Hello")
    (tmp_path / "proj-b" / "doc.md").write_text("# World")

    toml = tmp_path / "recall.toml"
    toml.write_text(f'[[sources]]\nroot = "{tmp_path}"\nglob = "**/*.md"\n')
    cfg = load_config(toml)

    discovered = cfg.discover_projects()
    names = {p.name for p in discovered}
    assert "proj-a" in names
    assert "proj-b" in names


def test_discover_projects_skips_excluded_dirs(tmp_path):
    (tmp_path / "proj-a").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "proj-a" / "doc.md").write_text("# Hello")
    (tmp_path / "node_modules" / "doc.md").write_text("# Should be excluded")

    toml = tmp_path / "recall.toml"
    toml.write_text(
        f'[[sources]]\nroot = "{tmp_path}"\nglob = "**/*.md"\nexclude = ["node_modules"]\n'
    )
    cfg = load_config(toml)

    discovered = cfg.discover_projects()
    names = {p.name for p in discovered}
    assert "proj-a" in names
    assert "node_modules" not in names


def test_discover_projects_skips_dirs_without_matching_files(tmp_path):
    (tmp_path / "has-docs").mkdir()
    (tmp_path / "empty-dir").mkdir()
    (tmp_path / "has-docs" / "readme.md").write_text("# Hello")

    toml = tmp_path / "recall.toml"
    toml.write_text(f'[[sources]]\nroot = "{tmp_path}"\nglob = "**/*.md"\n')
    cfg = load_config(toml)

    discovered = cfg.discover_projects()
    names = {p.name for p in discovered}
    assert "has-docs" in names
    assert "empty-dir" not in names


def test_all_projects_explicit_takes_precedence_over_discovered(tmp_path):
    (tmp_path / "myproj").mkdir()
    (tmp_path / "myproj" / "doc.md").write_text("# Hello")

    toml = tmp_path / "recall.toml"
    toml.write_text(
        f'[[projects]]\nname = "myproj"\npath = "{tmp_path}/myproj/docs"\ncollection = "myproj-custom"\n\n'
        f'[[sources]]\nroot = "{tmp_path}"\nglob = "**/*.md"\n'
    )
    cfg = load_config(toml)

    all_projects = cfg.all_projects()
    myproj = next(p for p in all_projects if p.name == "myproj")
    assert myproj.collection == "myproj-custom"


def test_all_projects_includes_both_explicit_and_discovered(tmp_path):
    (tmp_path / "auto-proj").mkdir()
    (tmp_path / "auto-proj" / "doc.md").write_text("# Hello")

    toml = tmp_path / "recall.toml"
    toml.write_text(
        f'[[projects]]\nname = "explicit-proj"\npath = "{tmp_path}"\ncollection = "explicit"\n\n'
        f'[[sources]]\nroot = "{tmp_path}"\nglob = "**/*.md"\n'
    )
    cfg = load_config(toml)

    names = {p.name for p in cfg.all_projects()}
    assert "explicit-proj" in names
    assert "auto-proj" in names


def test_discover_projects_uses_subdir_name_as_collection(tmp_path):
    (tmp_path / "my-project").mkdir()
    (tmp_path / "my-project" / "readme.md").write_text("# Hello")

    toml = tmp_path / "recall.toml"
    toml.write_text(f'[[sources]]\nroot = "{tmp_path}"\nglob = "**/*.md"\n')
    cfg = load_config(toml)

    discovered = cfg.discover_projects()
    proj = next(p for p in discovered if p.name == "my-project")
    assert proj.collection == "my-project"
    assert proj.name == "my-project"
