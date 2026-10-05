from __future__ import annotations

import json
import subprocess
from pathlib import Path

from recall.config import GraphifyConfig
from recall.graphify_adapter import build_graph, cache_dir, parse_graph

ROOT = Path("/repo")


def _node(node_id, label, source_file, location, **extra):
    return {"id": node_id, "label": label, "source_file": source_file, "source_location": location, **extra}


def _edge(source, target, relation, confidence="EXTRACTED"):
    return {"source": source, "target": target, "relation": relation, "confidence": confidence}


GRAPH = {
    "nodes": [
        _node("mod", "mod.py", "pkg/mod.py", "L1", community=3, community_name="mod.py"),
        _node("cls", "Service", "pkg/mod.py", "L5", community=3, community_name="core"),
        _node("run", ".run()", "pkg/mod.py", "L9", community=3, community_name="core"),
        _node("helper", "helper()", "pkg/util.py", "L2", community=4, community_name="utils"),
        _node("other_run", ".run()", "pkg/other.py", "L3", community=5, community_name="x"),
        _node("os", "os", "", None),
        _node("abs", "absfn()", "/repo/pkg/abs.py", "L7"),
    ],
    "links": [
        _edge("cls", "run", "method"),
        _edge("run", "helper", "calls"),
        _edge("run", "os", "calls"),
        _edge("run", "other_run", "uses", "INFERRED"),
        _edge("mod", "helper", "imports_from"),
        _edge("other_run", "cls", "inherits"),
        _edge("ghost", "run", "calls"),
    ],
}


def _index(**kwargs):
    return parse_graph(GRAPH, {"cls"}, "REPORT", ROOT, **kwargs)


def test_nodes_without_source_file_are_dropped_and_paths_normalized():
    index = _index()
    assert "os" not in index.nodes
    assert index.nodes["abs"]["source_file"] == "pkg/abs.py"
    assert index.by_location[("pkg/abs.py", 7)] == "abs"


def test_find_matches_by_file_and_def_line():
    index = _index()
    assert index.find("pkg/mod.py", 9, 8, 12, "method") == "run"
    assert index.find("pkg/mod.py", 5, 4, 20, "class") == "cls"


def test_find_falls_back_to_first_node_inside_the_range():
    index = _index()
    assert index.find("pkg/mod.py", None, 7, 12, "function") == "run"
    assert index.find("pkg/mod.py", None, 30, 40, "function") is None


def test_find_for_module_uses_file_node_and_windows_never_match():
    index = _index()
    assert index.find("pkg/mod.py", None, 1, 3, "module") == "mod"
    assert index.find("pkg/mod.py", None, 1, 99, "window") is None


def test_qualified_names_prefix_methods_with_their_class():
    index = _index()
    assert index.qualified["run"] == "Service.run"
    assert index.qualified["helper"] == "helper"
    assert index.qualified["other_run"] == "run"


def test_info_reports_community_god_node_and_related_symbols():
    info = _index().info("run", "method")
    assert info.community_id == 3
    assert info.community_name == "core"
    assert info.is_god_node is False
    assert info.related_symbols == ["helper"]
    assert _index().info("cls", "class").is_god_node is True


def test_related_symbols_exclude_inferred_external_and_unknown_edges():
    related = _index().info("run", "method").related_symbols
    assert "os" not in related and "run" not in related


def test_related_includes_incoming_edges_and_module_uses_imports_from():
    index = _index()
    assert index.info("helper", "function").related_symbols == ["Service.run"]
    assert index.info("cls", "class").related_symbols == ["run"]
    assert index.info("mod", "module").related_symbols == ["helper"]
    assert "mod.py" not in index.info("helper", "function").related_symbols


def test_related_is_capped():
    graph = {
        "nodes": [_node("a", "a()", "f.py", "L1")] + [_node(f"n{i}", f"n{i}()", "f.py", f"L{i + 2}") for i in range(20)],
        "links": [_edge("a", f"n{i}", "calls") for i in range(20)],
    }
    index = parse_graph(graph, set(), "", ROOT, related_max=5)
    assert len(index.info("a", "function").related_symbols) == 5


def test_god_labels_are_qualified_and_sorted():
    assert _index().god_labels() == ["Service"]


class _Runner:
    def __init__(self, out_graph=GRAPH, god=None, fail=None):
        self.calls = []
        self.out_graph = out_graph
        self.god = god if god is not None else [{"id": "cls", "label": "Service", "degree": 4}]
        self.fail = fail

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.fail:
            raise self.fail
        out = Path(kwargs["env"]["GRAPHIFY_OUT"])
        if cmd[1] == "update":
            (out / "graph.json").write_text(json.dumps(self.out_graph))
            (out / "GRAPH_REPORT.md").write_text("# Report")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, json.dumps(self.god), "")


def test_build_graph_runs_graphify_with_out_dir_and_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runner = _Runner()

    index = build_graph(tmp_path, "myrepo", GraphifyConfig(god_nodes_top=7), runner=runner, which=lambda n: "/bin/graphify")

    assert index is not None and index.report == "# Report"
    update, god = runner.calls
    assert update[0] == ["graphify", "update", str(tmp_path.resolve()), "--force"]
    assert god[0] == ["graphify", "god-nodes", "--top", "7", "--json"]
    for _, kwargs in runner.calls:
        assert kwargs["env"]["GRAPHIFY_OUT"] == str(cache_dir("myrepo"))
        assert kwargs["cwd"] == tmp_path.resolve()
        assert "shell" not in kwargs
    assert cache_dir("myrepo") == tmp_path / "cache" / "recall" / "graphify" / "myrepo"
    assert index.god_ids == {"cls"}


def test_build_graph_returns_none_when_graphify_missing(tmp_path, caplog):
    index = build_graph(tmp_path, "r", GraphifyConfig(), runner=_Runner(), which=lambda n: None)
    assert index is None
    assert "not found" in caplog.text


def test_build_graph_returns_none_on_timeout_or_bad_output(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    timeout = _Runner(fail=subprocess.TimeoutExpired("graphify", 1))
    assert build_graph(tmp_path, "r", GraphifyConfig(), runner=timeout, which=lambda n: "x") is None

    broken = _Runner(god=[{"no_id": 1}])
    assert build_graph(tmp_path, "r", GraphifyConfig(), runner=broken, which=lambda n: "x") is None
    assert "failed" in caplog.text


def test_build_graph_without_report_file_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    runner = _Runner()
    original = runner.__call__

    def no_report(cmd, **kwargs):
        result = original(cmd, **kwargs)
        report = Path(kwargs["env"]["GRAPHIFY_OUT"]) / "GRAPH_REPORT.md"
        report.unlink(missing_ok=True)
        return result

    index = build_graph(tmp_path, "r", GraphifyConfig(), runner=no_report, which=lambda n: "x")
    assert index is not None and index.report == ""
