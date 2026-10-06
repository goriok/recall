from __future__ import annotations

from recall.code_chunker import chunk_code
from recall.path_labels import path_labels
from recall.yaml_chunker import yaml_spans

VALUES = """base-webapp:
  namespace:
    enabled: false
  # runs smoke tests
  cronJob:
    enabled: false
    schedule: 0 * * * *
    command: /smoke_tests/run.sh
  image:
    repository: gcr.io/x/vpc-api
    tag: ffc29aec
  service:
    type: ClusterIP
    port: 80
"""


def _by_symbol(spans):
    return {s.symbol: s for s in spans}


def _lines(text, span):
    return text.splitlines()[span.start - 1 : span.end]


def test_small_top_level_keys_are_packed_into_one_span():
    chart = "apiVersion: v2\nname: 'vpc-api'\ntype: application\nversion: '0.5.2'\n"
    spans = yaml_spans(chart, max_chars=4000)
    assert [(s.start, s.end, s.symbol, s.kind) for s in spans] == [(1, 4, "apiVersion..version", "yaml_key")]


def test_single_small_key_keeps_its_name():
    spans = yaml_spans("replicaCount: 5\n", max_chars=4000)
    assert [s.symbol for s in spans] == ["replicaCount"]


def test_oversized_key_descends_to_children_with_dotted_path():
    spans = yaml_spans(VALUES, max_chars=60)
    symbols = _by_symbol(spans)
    assert "base-webapp.cronJob" in symbols
    cron = symbols["base-webapp.cronJob"]
    assert _lines(VALUES, cron)[0] == "  # runs smoke tests"
    schedule = next(s for s in spans if "schedule: 0 * * * *" in "\n".join(_lines(VALUES, s)))
    assert schedule.symbol.startswith("base-webapp.cronJob.")
    assert "base-webapp.image" in symbols
    assert "tag: ffc29aec" in "\n".join(_lines(VALUES, symbols["base-webapp.image"]))
    assert all(s.start <= s.end for s in spans)


def test_spans_do_not_overlap_and_stay_in_order():
    spans = yaml_spans(VALUES, max_chars=60)
    assert [(s.start, s.end) for s in spans] == sorted((s.start, s.end) for s in spans)
    assert all(a.end < b.start for a, b in zip(spans, spans[1:]))


def test_header_of_split_key_is_its_own_span():
    text = "outer:\n  a:\n    x: 1\n    y: 2\n  b:\n    z: 3\n    w: 4\n"
    spans = yaml_spans(text, max_chars=30)
    assert [s.symbol for s in spans][0] == "outer"
    assert _lines(text, spans[0]) == ["outer:"]


def test_kubernetes_multi_document_keeps_documents_apart():
    text = "kind: Service\nspec:\n  port: 80\n---\nkind: Deployment\nspec:\n  replicas: 2\n"
    spans = yaml_spans(text, max_chars=4000)
    assert all("---" not in "\n".join(_lines(text, s)) for s in spans)
    assert len(spans) >= 2


def test_helm_template_falls_back_to_windows():
    assert yaml_spans("metadata:\n  name: {{ .Release.Name }}\n", max_chars=4000) is None


def test_file_without_mapping_keys_falls_back():
    assert yaml_spans("- a\n- b\n", max_chars=4000) is None
    assert yaml_spans("# only a comment\n", max_chars=4000) is None


def test_key_larger_than_budget_without_children_stays_one_span():
    text = "script: |\n" + "  echo hello world\n" * 20
    spans = yaml_spans(text, max_chars=50)
    assert [(s.start, s.end) for s in spans] == [(1, 21)]


def test_chunk_code_uses_yaml_spans_for_yaml_files():
    chunks = chunk_code(VALUES, file_path="v/values.yaml", repo_name="r", max_chars=60)
    assert "base-webapp.cronJob" in {c.symbol_name for c in chunks}
    assert {c.kind for c in chunks} == {"yaml_key"}


def test_chunk_code_splits_oversized_leaf_by_budget():
    text = "script: |\n" + "  echo hello world\n" * 20
    chunks = chunk_code(text, file_path="ci.yml", repo_name="r", max_chars=80)
    assert len(chunks) > 1
    assert all(c.symbol_name == "script" for c in chunks)


def test_chunk_ids_are_stable_across_runs():
    a = chunk_code(VALUES, file_path="v.yaml", repo_name="r", max_chars=60)
    b = chunk_code(VALUES, file_path="v.yaml", repo_name="r", max_chars=60)
    assert [c.id for c in a] == [c.id for c in b]
    assert len({c.id for c in a}) == len(a)


TEMPLATES = [
    "{env}/{region}/dc/{dc}/override/{product}/{chart}/*",
    "{env}/{region}/dc/{dc}/{cell}/{product}/{chart}/*",
    "{env}/{region}/service/{product}/{chart}/*",
]


def test_path_labels_service_layout():
    assert path_labels("prod/ne1/service/vpc/vpc-api/values.yaml", TEMPLATES) == {
        "env": "prod", "region": "ne1", "product": "vpc", "chart": "vpc-api",
    }


def test_path_labels_first_matching_template_wins():
    labels = path_labels("pre-prod/ne1/dc/yel/override/mcr/harbor/config-dc.yaml", TEMPLATES)
    assert labels == {"env": "pre-prod", "region": "ne1", "dc": "yel", "product": "mcr", "chart": "harbor"}
    cell = path_labels("pre-prod/ne1/dc/yel/cell-1/cloud-events/worker/config-cell.yaml", TEMPLATES)
    assert cell["cell"] == "cell-1"


def test_path_labels_no_match_or_no_templates():
    assert path_labels("README.md", TEMPLATES) == {}
    assert path_labels("prod/ne1/service/vpc/vpc-api/values.yaml", None) == {}
    assert path_labels("prod/ne1/service/vpc/vpc-api/values.yaml", []) == {}


def test_chunk_code_prefixes_embed_text_with_labels():
    chunks = chunk_code(
        VALUES,
        file_path="prod/ne1/service/vpc/vpc-api/values.yaml",
        repo_name="r",
        max_chars=60,
        path_labels=TEMPLATES,
    )
    first_line = chunks[0].embed_text.splitlines()[0]
    assert first_line == "# env=prod region=ne1 product=vpc chart=vpc-api"
    assert "prod/ne1/service/vpc/vpc-api/values.yaml:" in chunks[0].embed_text

