import pytest
from pathlib import Path
from recall.config import load_config, ConfigError, Config, QdrantConfig, EmbeddingConfig


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_config_returns_config_with_defaults(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text("[qdrant]\nhost = 'localhost'\nport = 6333\n")
    cfg = load_config(toml)
    assert isinstance(cfg, Config)
    assert cfg.qdrant.host == "localhost"
    assert cfg.qdrant.port == 6333


def test_load_config_raises_when_file_missing(tmp_path):
    with pytest.raises(ConfigError, match="recall.toml not found"):
        load_config(tmp_path / "recall.toml")


def test_load_config_parses_projects(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text(
        '[qdrant]\nhost = "localhost"\n\n'
        '[[projects]]\nname = "foo"\npath = "~/sources/foo"\ncollection = "foo"\nglob = "**/*.md"\n'
    )
    cfg = load_config(toml)
    assert len(cfg.projects) == 1
    assert cfg.projects[0].name == "foo"
    assert cfg.projects[0].collection == "foo"


def test_load_config_project_lookup(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text(
        '[[projects]]\nname = "bar"\npath = "~/sources/bar"\ncollection = "bar"\n'
    )
    cfg = load_config(toml)
    project = cfg.project("bar")
    assert project.name == "bar"


def test_load_config_project_lookup_raises_for_unknown(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text("[qdrant]\nhost = 'localhost'\n")
    cfg = load_config(toml)
    with pytest.raises(ConfigError, match="unknown project 'nope'"):
        cfg.project("nope")


def test_qdrant_url():
    q = QdrantConfig(host="myhost", port=1234)
    assert q.url == "http://myhost:1234"


def test_load_config_embedding_defaults(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text("[qdrant]\nhost = 'localhost'\n")
    cfg = load_config(toml)
    assert cfg.embedding.model == "nomic-embed-text"
    assert cfg.embedding.provider == "ollama"


def test_load_config_embedding_custom(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text(
        '[embedding]\nmodel = "all-minilm"\nprovider = "ollama"\nollama_host = "http://remote:11434"\n'
    )
    cfg = load_config(toml)
    assert cfg.embedding.model == "all-minilm"
    assert cfg.embedding.ollama_host == "http://remote:11434"
