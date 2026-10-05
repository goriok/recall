from __future__ import annotations

import subprocess

import pytest

from recall.discovery import DiscoveryError, discover, expand_braces, matches_any


def _write(root, rel, content="x = 1\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _names(result, root):
    return sorted(p.relative_to(root).as_posix() for p in result.files)


def test_expand_braces_expands_alternatives():
    assert sorted(expand_braces("**/*.{py,go}")) == ["**/*.go", "**/*.py"]
    assert expand_braces("*.md") == ["*.md"]


def test_matches_any_handles_double_star_and_braces():
    assert matches_any("a/b/c.py", ["**/*.{py,go}"])
    assert matches_any("c.py", ["**/*.py"])
    assert not matches_any("a/c.txt", ["**/*.py"])
    assert not matches_any("a/b/c.py", ["*.py"])


def test_discover_filters_by_glob_and_excludes(tmp_path):
    _write(tmp_path, "a.py")
    _write(tmp_path, "sub/b.py")
    _write(tmp_path, "node_modules/c.py")
    _write(tmp_path, "notes.txt")

    result = discover(tmp_path, ["**/*.py"], ["node_modules"], [], 10_000)

    assert _names(result, tmp_path) == ["a.py", "sub/b.py"]


def test_discover_skips_denylisted_files(tmp_path):
    _write(tmp_path, "app.py")
    _write(tmp_path, ".env", "TOKEN=1")
    _write(tmp_path, "keys/server.pem", "pem")
    _write(tmp_path, "db_credentials.py")

    result = discover(tmp_path, ["**/*", "**/.env"], [], [".env", "*.pem", "*credentials*"], 10_000)

    assert _names(result, tmp_path) == ["app.py"]
    assert result.skipped["denylist"] == 3


def test_discover_skips_large_and_binary_files(tmp_path):
    _write(tmp_path, "small.py")
    _write(tmp_path, "big.py", "x" * 500)
    (tmp_path / "blob.py").write_bytes(b"abc\0def")

    result = discover(tmp_path, ["**/*.py"], [], [], 100)

    assert _names(result, tmp_path) == ["small.py"]
    assert result.skipped["too_large"] == 1
    assert result.skipped["binary"] == 1


def test_discover_skips_symlink_pointing_outside_root(tmp_path):
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("token = 1")
    _write(root, "ok.py")
    (root / "link.py").symlink_to(outside / "secret.py")

    result = discover(root, ["**/*.py"], [], [], 10_000)

    assert _names(result, root) == ["ok.py"]
    assert result.skipped["outside_root"] == 1


def test_discover_raises_when_nothing_matches(tmp_path):
    _write(tmp_path, "a.txt")
    with pytest.raises(DiscoveryError, match="no files"):
        discover(tmp_path, ["**/*.py"], [], [], 10_000)


def test_discover_raises_for_missing_directory(tmp_path):
    with pytest.raises(DiscoveryError, match="not a directory"):
        discover(tmp_path / "ghost", ["**/*.py"], [], [], 10_000)


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_discover_in_git_repo_respects_gitignore_and_handles_odd_names(tmp_path):
    _git(tmp_path, "init", "-q")
    _write(tmp_path, ".gitignore", "ignored.py\n")
    _write(tmp_path, "kept.py")
    _write(tmp_path, "ignored.py")
    _write(tmp_path, "ação.py")
    _write(tmp_path, "gone.py")
    _git(tmp_path, "add", "-A")
    (tmp_path / "gone.py").unlink()

    result = discover(tmp_path, ["**/*.py"], [], [], 10_000)

    assert _names(result, tmp_path) == ["ação.py", "kept.py"]


def test_discover_git_subdirectory_returns_paths_under_it(tmp_path):
    _git(tmp_path, "init", "-q")
    _write(tmp_path, "top.py")
    _write(tmp_path, "pkg/inner.py")

    result = discover(tmp_path / "pkg", ["**/*.py"], [], [], 10_000)

    assert _names(result, tmp_path / "pkg") == ["inner.py"]


def test_denylist_is_case_insensitive(tmp_path):
    _write(tmp_path, "app.py")
    _write(tmp_path, ".ENV", "TOKEN=1")
    _write(tmp_path, "Credentials.json", "{}")
    _write(tmp_path, "keys/ID_RSA", "key")

    result = discover(tmp_path, ["**/*", "**/.*"], [], [".env", "*credentials*", "id_*"], 10_000)

    assert _names(result, tmp_path) == ["app.py"]
    assert result.skipped["denylist"] == 3


def test_symlink_to_a_denied_file_inside_the_root_is_not_indexed(tmp_path):
    _write(tmp_path, "ok.py")
    _write(tmp_path, ".env", "TOKEN=1")
    (tmp_path / "innocent.txt").symlink_to(tmp_path / ".env")
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "notes.md").symlink_to(tmp_path / "ok.py")

    result = discover(tmp_path, ["**/*", "**/.*"], [], [".env"], 10_000)

    assert _names(result, tmp_path) == ["deep/notes.md", "ok.py"]
    assert result.skipped["denylist"] == 2
