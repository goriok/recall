from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{skill_md} has no frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _pyproject_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_every_plugin_manifest_carries_the_package_version():
    version = _pyproject_version()
    assert _json(ROOT / ".claude-plugin" / "plugin.json")["version"] == version
    assert _json(ROOT / "plugin.json")["version"] == version


def test_claude_marketplace_points_at_the_repo_root_plugin():
    marketplace = _json(ROOT / ".claude-plugin" / "marketplace.json")
    plugin = _json(ROOT / ".claude-plugin" / "plugin.json")
    assert [p["name"] for p in marketplace["plugins"]] == [plugin["name"]] == ["recall"]
    assert marketplace["plugins"][0]["source"] == "./"


def test_hermes_portable_manifest_uses_the_agent_plugins_v1_schema():
    manifest = _json(ROOT / "plugin.json")
    assert manifest["$schema"] == PLUGIN_SCHEMA
    assert re.fullmatch(r"[a-z0-9][a-z0-9.-]*", manifest["name"])
    assert set(manifest) <= {
        "$schema", "name", "version", "description", "author", "homepage",
        "repository", "license", "keywords", "extensions",
    }


def test_mcp_servers_are_the_same_command_for_every_host():
    claude = _json(ROOT / ".claude-plugin" / "plugin.json")["mcpServers"]["recall"]
    hermes = _json(ROOT / "mcp.json")
    assert hermes["$schema"] == MCP_SCHEMA
    server = hermes["mcpServers"]["recall"]
    assert server["type"] == "stdio"
    assert (server["command"], server["args"]) == (claude["command"], claude["args"])
    assert server["args"][-1] == "recall-mcp"
    assert "env" not in server and "headers" not in server


def test_agy_plugin_shares_the_single_skills_directory():
    link = ROOT / "plugins" / "recall" / "skills"
    assert link.is_symlink()
    assert link.resolve() == SKILLS.resolve()
    assert _json(ROOT / "plugins" / "recall" / "mcp_config.json")["mcpServers"]["recall"]["command"] == "recall-mcp"


def test_skills_follow_the_shared_agent_skills_constraints():
    skills = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    assert [s.name for s in skills] == ["recall-code", "recall-ingest", "recall-search"]
    for skill in skills:
        fields = _frontmatter(skill / "SKILL.md")
        assert fields["name"] == skill.name
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"])
        assert 1 <= len(fields["description"]) <= 1024


def test_skill_documents_every_mcp_tool():
    body = (SKILLS / "recall-search" / "SKILL.md").read_text(encoding="utf-8")
    for tool in ("search_docs", "search_code", "explain_architecture", "list_sources"):
        assert tool in body


def test_every_mcp_tool_is_registered_and_every_skill_refers_only_to_real_ones():
    import asyncio

    from recall.mcp_server import mcp

    registered = {t.name for t in asyncio.run(mcp.list_tools())}
    assert registered == {"search_docs", "search_code", "explain_architecture", "list_sources"}
    known = registered | {"search_code_mcp"}
    for skill in SKILLS.iterdir():
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        for name in re.findall(r"`((?:search|list|explain)_[a-z_]+)(?:\(|`)", text):
            assert name in known, f"{skill.name} mentions unknown tool {name}"


def test_cross_references_between_skills_point_to_existing_skills():
    names = {p.name for p in SKILLS.iterdir()}
    for skill in SKILLS.iterdir():
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        for ref in re.findall(r"skill `(recall-[a-z]+)`", text):
            assert ref in names, f"{skill.name} refers to missing skill {ref}"


@pytest.mark.parametrize("path", ["plugin.json", "mcp.json", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"])
def test_manifests_do_not_embed_secrets(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert not re.search(r"(?i)(api[_-]?key|token|secret)\"\s*:\s*\"[^\"$]", text)
