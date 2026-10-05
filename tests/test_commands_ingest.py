import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path
from recall.cli import app
from recall.config import Config, QdrantConfig, EmbeddingConfig, ProjectConfig

runner = CliRunner()

FAKE_PROJECT = ProjectConfig(
    name="test-proj",
    path="/tmp/fake-docs",
    collection="test-proj",
    glob="**/*.md",
)

FAKE_CONFIG = Config(
    qdrant=QdrantConfig(host="localhost", port=6333),
    embedding=EmbeddingConfig(model="nomic-embed-text", provider="ollama"),
    projects=[FAKE_PROJECT],
)


def test_ingest_command_exists():
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "ingest" in result.output.lower()


def test_ingest_unknown_project_shows_error():
    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=FAKE_CONFIG):
        result = runner.invoke(app, ["ingest", "no-such-project"])
    assert result.exit_code != 0
    assert "no-such-project" in result.output


def test_ingest_calls_indexer_for_project(tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Hello\n\nContent here.\n")

    project = ProjectConfig(
        name="mypkg",
        path=str(tmp_path),
        collection="mypkg",
        glob="**/*.md",
    )
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "qdrant")),
        embedding=EmbeddingConfig(),
        projects=[project],
    )

    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=config), \
         patch("recall.commands.ingest.index_project") as mock_index:
        result = runner.invoke(app, ["ingest", "mypkg"])

    assert result.exit_code == 0
    mock_index.assert_called_once()
    call_args = mock_index.call_args
    assert call_args[0][0] == project


def test_ingest_skips_missing_path(tmp_path):
    project = ProjectConfig(
        name="ghost",
        path="/nonexistent/path",
        collection="ghost",
    )
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "qdrant")),
        embedding=EmbeddingConfig(),
        projects=[project],
    )

    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=config), \
         patch("recall.commands.ingest.index_project") as mock_index:
        result = runner.invoke(app, ["ingest", "--all"])

    assert result.exit_code == 0
    mock_index.assert_not_called()
    assert "skipping" in result.output


def test_ingest_all_calls_indexer_for_each_project(tmp_path):
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "qdrant")),
        embedding=EmbeddingConfig(),
        projects=[
            ProjectConfig(name="a", path=str(tmp_path), collection="a"),
            ProjectConfig(name="b", path=str(tmp_path), collection="b"),
        ],
    )

    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=config), \
         patch("recall.commands.ingest.index_project") as mock_index:
        result = runner.invoke(app, ["ingest", "--all"])

    assert result.exit_code == 0
    assert mock_index.call_count == 2


from recall.adapters.openai_embedding_provider import EmbeddingProviderError
from recall.config import RepoConfig, SourceConfig
from recall.discovery import DiscoveryError
from recall.indexer import IndexReport
from recall.meta import ModelMismatchError
from tests.fakes import FakeEmbeddingProvider, FakeVectorStore


def _run(config, args, store=None, indexer=None):
    store = store if store is not None else FakeVectorStore()
    with patch("recall.commands.ingest.find_config", return_value=Path("/fake/recall.toml")), \
         patch("recall.commands.ingest.load_config", return_value=config), \
         patch("recall.commands.ingest._open_store", return_value=store), \
         patch("recall.commands.ingest.ProviderResolver") as resolver_cls, \
         patch("recall.commands.ingest.index_project", side_effect=indexer or (lambda *a, **k: 1)) as mock_index:
        resolver_cls.return_value.for_project.return_value = FakeEmbeddingProvider()
        result = runner.invoke(app, args)
    return result, mock_index, store


def _config_with_docs(tmp_path):
    return Config(
        qdrant=QdrantConfig(path=str(tmp_path / "q")),
        projects=[ProjectConfig(name="a", path=str(tmp_path), collection="a")],
    )


def test_ingest_passes_provider_for_each_project_and_recreate_flag(tmp_path):
    result, mock_index, _ = _run(_config_with_docs(tmp_path), ["ingest", "a", "--recreate"])

    assert result.exit_code == 0
    assert mock_index.call_args.kwargs["recreate"] is True
    assert isinstance(mock_index.call_args.kwargs["embedding_provider"], FakeEmbeddingProvider)


def test_ingest_prints_summary_lines_from_the_report(tmp_path):
    def indexer(project, **kwargs):
        report: IndexReport = kwargs["report"]
        report.removed_files = 2
        report.skipped["too_large"] = 3
        report.graph = False
        report.warnings.append("something worth knowing")
        return 5

    result, _, _ = _run(_config_with_docs(tmp_path), ["ingest", "a"], indexer=indexer)

    assert "5 chunks indexed" in result.output
    assert "removed 2 deleted file(s)" in result.output
    assert "3 too_large" in result.output
    assert "graph metadata unavailable" in result.output
    assert "something worth knowing" in result.output


@pytest.mark.parametrize(
    "error",
    [DiscoveryError("no files under /x"), ModelMismatchError("use --recreate"), EmbeddingProviderError("endpoint returned HTTP 401")],
)
def test_ingest_reports_project_failure_and_exits_nonzero_after_the_rest(tmp_path, error):
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "q")),
        projects=[
            ProjectConfig(name="bad", path=str(tmp_path), collection="bad"),
            ProjectConfig(name="good", path=str(tmp_path), collection="good"),
        ],
    )

    def indexer(project, **kwargs):
        if project.name == "bad":
            raise error
        return 1

    result, mock_index, _ = _run(config, ["ingest", "--all"], indexer=indexer)

    assert result.exit_code == 1
    assert str(error) in result.output
    assert mock_index.call_count == 2
    assert "good: 1 chunks indexed" in result.output


def test_ingest_all_warns_about_orphan_collections_and_prune_drops_them(tmp_path):
    topics = tmp_path / "ctx" / "topics"
    (topics / "live").mkdir(parents=True)
    (topics / "live" / "a.md").write_text("# A\n\nbody\n")
    config = Config(qdrant=QdrantConfig(path=str(tmp_path / "q")), sources=[SourceConfig(root=str(topics))])

    def seeded():
        store = FakeVectorStore()
        for name in ("ctx.live", "ctx.gone", "unrelated"):
            store.recreate_collection(name, 4)
        return store

    warned, _, store = _run(config, ["ingest", "--all"], store=seeded())
    assert "orphan collection (topic gone): ctx.gone" in warned.output
    assert "ctx.gone" in store.collections and "unrelated" not in warned.output

    pruned, _, store = _run(config, ["ingest", "--all", "--prune"], store=seeded())
    assert "pruned orphan collection: ctx.gone" in pruned.output
    assert "ctx.gone" not in store.collections
    assert {"ctx.live", "unrelated"} <= set(store.collections)


def test_ingest_without_all_does_not_look_for_orphans(tmp_path):
    result, _, _ = _run(_config_with_docs(tmp_path), ["ingest", "a"])
    assert "orphan" not in result.output


def test_ingest_ensures_remote_qdrant_with_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("QD_KEY", "k")
    config = Config(
        qdrant=QdrantConfig(host="qdrant.internal", api_key_env="QD_KEY"),
        projects=[ProjectConfig(name="a", path=str(tmp_path), collection="a")],
    )
    with patch("recall.commands.ingest.ensure_qdrant") as ensure:
        _run(config, ["ingest", "a"])
    ensure.assert_called_once_with("http://qdrant.internal:6333", "k")


def test_open_store_explains_embedded_lock_conflicts(tmp_path):
    from recall.commands.ingest import _open_store
    import typer

    with patch(
        "recall.commands.ingest.QdrantVectorStore",
        side_effect=RuntimeError("Storage folder is already accessed by another instance of Qdrant client"),
    ):
        with pytest.raises(typer.Exit):
            _open_store(Config(qdrant=QdrantConfig(path=str(tmp_path))))


def test_open_store_reraises_unrelated_errors(tmp_path):
    from recall.commands.ingest import _open_store

    with patch("recall.commands.ingest.QdrantVectorStore", side_effect=RuntimeError("disk full")):
        with pytest.raises(RuntimeError, match="disk full"):
            _open_store(Config(qdrant=QdrantConfig(path=str(tmp_path))))


def test_ingest_resolves_code_repos_by_name(tmp_path):
    config = Config(
        qdrant=QdrantConfig(path=str(tmp_path / "q")),
        repos=[RepoConfig(name="svc", root=str(tmp_path))],
    )
    result, mock_index, _ = _run(config, ["ingest", "svc"])

    assert result.exit_code == 0
    assert mock_index.call_args[0][0].kind == "code"
