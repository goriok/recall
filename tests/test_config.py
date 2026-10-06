import json

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


def test_project_config_has_default_path_exclude(tmp_path):
    toml = tmp_path / "recall.toml"
    toml.write_text('[[projects]]\nname = "x"\npath = "~/x"\ncollection = "x"\n')
    cfg = load_config(toml)
    assert "node_modules" in cfg.projects[0].path_exclude
    assert ".git" in cfg.projects[0].path_exclude


def test_source_config_propagates_path_exclude_to_discovered(tmp_path):
    proj_dir = tmp_path / "myproject"
    proj_dir.mkdir()
    (proj_dir / "README.md").write_text("# Hello")

    toml = tmp_path / "recall.toml"
    toml.write_text(f'[[sources]]\nroot = "{tmp_path}"\nglob = "**/*.md"\n')
    cfg = load_config(toml)
    projects = cfg.discover_projects()
    assert len(projects) == 1
    assert "node_modules" in projects[0].path_exclude


def test_load_config_embedding_custom(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "remote")
    toml = tmp_path / "recall.toml"
    toml.write_text(
        '[embedding]\nmodel = "all-minilm"\nprovider = "ollama"\nollama_host = "http://remote:11434"\n'
    )
    cfg = load_config(toml)
    assert cfg.embedding.model == "all-minilm"
    assert cfg.embedding.ollama_host == "http://remote:11434"


from recall.config import ProjectConfig, RepoConfig, SourceConfig


def _write(tmp_path, body):
    toml = tmp_path / "recall.toml"
    toml.write_text(body)
    return load_config(toml)


def test_qdrant_url_uses_https_and_api_key_comes_from_env(monkeypatch):
    monkeypatch.setenv("QD_KEY", "s3")
    cfg = QdrantConfig(host="q.internal", port=443, https=True, api_key_env="QD_KEY")
    assert cfg.url == "https://q.internal:443"
    assert cfg.api_key() == "s3"
    assert QdrantConfig(host="q").api_key() is None
    assert QdrantConfig(path="/x").url is None


def test_load_config_parses_qdrant_grpc_https_and_key_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "embeddings.example,q")
    cfg = _write(
        tmp_path,
        '[qdrant]\nhost = "q"\nprefer_grpc = true\ngrpc_port = 7000\nhttps = true\napi_key_env = "K"\n',
    )
    assert (cfg.qdrant.prefer_grpc, cfg.qdrant.grpc_port, cfg.qdrant.https, cfg.qdrant.api_key_env) == (True, 7000, True, "K")


def test_load_config_parses_embedding_table_with_endpoint_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "embeddings.example,q")
    cfg = _write(
        tmp_path,
        '[embedding]\nprovider = "openai"\nmodel = "nomic-embed-text-v1-5"\nbase_url = "https://embeddings.example/v1"\n'
        'api_key_env = "RECALL_EMBEDDING_API_KEY"\nbatch_size = 16\n',
    )
    assert cfg.embedding.provider == "openai"
    assert cfg.embedding.base_url == "https://embeddings.example/v1"
    assert cfg.embedding.api_key_env == "RECALL_EMBEDDING_API_KEY"
    assert cfg.embedding.batch_size == 16


@pytest.mark.parametrize("size", [0, 33, 64])
def test_load_config_rejects_endpoint_batch_size_above_limit(tmp_path, size):
    with pytest.raises(ConfigError, match="between 1 and 32"):
        _write(tmp_path, f"[embedding]\nbatch_size = {size}\n")


def test_per_source_and_per_repo_embedding_override_inherits_global_values(tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "embeddings.example,q")
    cfg = _write(
        tmp_path,
        '[embedding]\nprovider = "openai"\nmodel = "m"\nbase_url = "https://embeddings.example/v1"\napi_key_env = "K"\n\n'
        '[[sources]]\nroot = "/ctx/topics"\n[sources.embedding]\nprovider = "ollama"\nmodel = "nomic-embed-text"\n\n'
        '[[repos]]\nname = "svc"\nroot = "/svc"\n',
    )
    source_embedding = cfg.sources[0].embedding
    assert source_embedding.provider == "ollama"
    assert source_embedding.base_url == "https://embeddings.example/v1"
    assert cfg.repos[0].embedding is None
    assert cfg.embedding_for(None).provider == "openai"
    assert cfg.embedding_for(cfg.repos[0].as_project()).provider == "openai"


def test_load_config_parses_repos_with_graphify_and_defaults(tmp_path):
    cfg = _write(
        tmp_path,
        '[[repos]]\nname = "svc"\nroot = "~/src/svc"\nglobs = ["**/*.{py,go}"]\nmax_chunk_chars = 2000\n'
        'window_lines = 30\n[repos.graphify]\nenabled = false\ntimeout_seconds = 10\ngod_nodes_top = 3\n\n'
        '[[repos]]\nroot = "/work/other-repo"\n',
    )
    svc, other = cfg.repos
    assert svc.collection == "code.svc"
    assert svc.globs == ["**/*.{py,go}"]
    assert (svc.max_chunk_chars, svc.window_lines) == (2000, 30)
    assert (svc.graphify.enabled, svc.graphify.timeout_seconds, svc.graphify.god_nodes_top) == (False, 10, 3)
    assert other.name == "other-repo"
    assert other.graphify.enabled is True
    assert ".env" in other.deny and "graphify-out" in other.path_exclude


def test_all_projects_include_repos_as_code_projects_and_lookup_works(tmp_path):
    cfg = Config(
        projects=[ProjectConfig(name="docs", path="/d", collection="docs")],
        repos=[RepoConfig(name="svc", root=str(tmp_path))],
    )
    names = [(p.name, p.kind) for p in cfg.all_projects()]
    assert names == [("docs", "docs"), ("svc", "code")]
    assert cfg.project("svc").collection == "code.svc"
    assert cfg.project_for_collection("code.svc").name == "svc"
    assert cfg.project_for_collection("svc").name == "svc"
    assert cfg.project_for_collection("nope") is None
    repo_project = cfg.project("svc")
    assert repo_project.effective_globs == ["**/*.py", "**/*.md"]
    assert repo_project.effective_repo_name == "svc"
    assert repo_project.resolved_repo_root == tmp_path


def test_explicit_project_wins_over_repo_with_same_name():
    cfg = Config(
        projects=[ProjectConfig(name="svc", path="/d", collection="svc")],
        repos=[RepoConfig(name="svc", root="/r")],
    )
    assert [p.kind for p in cfg.all_projects()] == ["docs"]


def test_discovered_projects_carry_repo_root_and_repo_name(tmp_path):
    topics = tmp_path / "my-ctx" / "topics"
    (topics / "auth").mkdir(parents=True)
    (topics / "auth" / "a.md").write_text("# A\n")
    cfg = Config(sources=[SourceConfig(root=str(topics))])

    [project] = cfg.discover_projects()

    assert project.name == "my-ctx.auth"
    assert project.repo_name == "my-ctx"
    assert project.resolved_repo_root == tmp_path / "my-ctx"
    assert cfg.source_prefixes() == {"my-ctx"}


def test_source_repo_root_can_be_overridden(tmp_path):
    topics = tmp_path / "ctx" / "topics"
    (topics / "t").mkdir(parents=True)
    (topics / "t" / "a.md").write_text("# A\n")
    source = SourceConfig(root=str(topics), repo_root=str(tmp_path))
    [project] = Config(sources=[source]).discover_projects()
    assert project.resolved_repo_root == tmp_path
    assert project.repo_name == tmp_path.name


def test_default_path_exclude_covers_obsidian_and_graphify_output():
    assert {".obsidian", "graphify-out", "target", "vendor"} <= set(ProjectConfig(name="a", path="/a", collection="a").path_exclude)



import recall.config as config_module
from recall.config import trusted_hosts

REMOTE_TOML = (
    '[embedding]\nprovider = "openai"\nmodel = "m"\nbase_url = "https://embeddings.example/v1"\n'
    'api_key_env = "AWS_SECRET_ACCESS_KEY"\n'
)


@pytest.fixture
def isolated_global(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "_GLOBAL_CONFIG", tmp_path / "global" / "recall.toml")
    monkeypatch.delenv("RECALL_TRUSTED_HOSTS", raising=False)
    return tmp_path / "global" / "recall.toml"


def test_local_config_cannot_send_an_env_key_to_an_untrusted_host(tmp_path, isolated_global):
    with pytest.raises(ConfigError, match="untrusted host 'embeddings.example'"):
        _write(tmp_path, REMOTE_TOML)


def test_local_config_cannot_exfiltrate_through_a_per_project_override(tmp_path, isolated_global):
    body = (
        '[embedding]\nmodel = "nomic-embed-text"\n\n[[sources]]\nroot = "/ctx/topics"\n'
        '[sources.embedding]\nprovider = "openai"\nbase_url = "https://evil.example/v1"\napi_key_env = "HOME"\n'
    )
    with pytest.raises(ConfigError, match="evil.example"):
        _write(tmp_path, body)


def test_local_config_cannot_send_a_qdrant_key_to_an_untrusted_host(tmp_path, isolated_global):
    with pytest.raises(ConfigError, match="untrusted host 'evil.example'"):
        _write(tmp_path, '[qdrant]\nhost = "evil.example"\nhttps = true\napi_key_env = "HOME"\n')


def test_host_declared_in_the_global_config_is_trusted_for_local_configs(tmp_path, isolated_global):
    isolated_global.parent.mkdir(parents=True)
    isolated_global.write_text(REMOTE_TOML.replace("AWS_SECRET_ACCESS_KEY", "RECALL_EMBEDDING_API_KEY"))

    cfg = _write(tmp_path, REMOTE_TOML.replace("AWS_SECRET_ACCESS_KEY", "RECALL_EMBEDDING_API_KEY"))

    assert cfg.embedding.base_url == "https://embeddings.example/v1"
    assert "embeddings.example" in trusted_hosts()


def test_local_config_cannot_pick_a_different_env_var_for_a_trusted_host(tmp_path, isolated_global):
    isolated_global.parent.mkdir(parents=True)
    isolated_global.write_text(REMOTE_TOML.replace("AWS_SECRET_ACCESS_KEY", "RECALL_EMBEDDING_API_KEY"))

    with pytest.raises(ConfigError, match=r"\$GITHUB_TOKEN is not authorized for 'embeddings.example'.*RECALL_EMBEDDING_API_KEY"):
        _write(tmp_path, REMOTE_TOML.replace("AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"))


def test_trusting_a_host_by_env_var_or_security_table_allows_any_key_for_it(tmp_path, isolated_global, monkeypatch):
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "embeddings.example")
    assert _write(tmp_path, REMOTE_TOML.replace("AWS_SECRET_ACCESS_KEY", "ANY_NAME")).embedding.api_key_env == "ANY_NAME"


@pytest.mark.parametrize(
    "body",
    [
        '[embedding]\nprovider = "ollama"\nollama_host = "http://evil.example:11434"\n',
        '[embedding]\nprovider = "openai"\nmodel = "m"\nbase_url = "https://evil.example/v1"\napi_key_env = "X"\n',
        '[qdrant]\nhost = "evil.example"\n',
        '[[sources]]\nroot = "/ctx/topics"\n[sources.embedding]\nprovider = "ollama"\nollama_host = "http://evil.example:11434"\n',
        '[[repos]]\nname = "r"\nroot = "/r"\n[repos.embedding]\nprovider = "ollama"\nollama_host = "http://evil.example"\n',
    ],
)
def test_local_config_cannot_send_indexed_content_to_an_untrusted_remote_even_without_a_key(body, tmp_path, isolated_global):
    with pytest.raises(ConfigError, match="untrusted host 'evil.example'"):
        _write(tmp_path, body)


def test_local_config_may_use_local_ollama_and_qdrant_without_any_declaration(tmp_path, isolated_global):
    cfg = _write(tmp_path, '[qdrant]\nhost = "localhost"\n[embedding]\nollama_host = "http://127.0.0.1:11434"\n')
    assert cfg.qdrant.host == "localhost"


def test_hosts_used_by_the_global_config_for_ollama_and_qdrant_are_trusted(tmp_path, isolated_global):
    isolated_global.parent.mkdir(parents=True)
    isolated_global.write_text('[qdrant]\nhost = "qdrant.internal"\n[embedding]\nollama_host = "http://gpu-box:11434"\n')

    cfg = _write(tmp_path, '[qdrant]\nhost = "qdrant.internal"\n[embedding]\nollama_host = "http://gpu-box:11434"\n')

    assert cfg.embedding.ollama_host == "http://gpu-box:11434"
    assert {"qdrant.internal", "gpu-box"} <= trusted_hosts()


def test_host_in_security_table_or_env_var_is_trusted(tmp_path, isolated_global, monkeypatch):
    isolated_global.parent.mkdir(parents=True)
    isolated_global.write_text('[security]\ntrusted_hosts = ["embeddings.example"]\n')
    assert _write(tmp_path, REMOTE_TOML).embedding.api_key_env == "AWS_SECRET_ACCESS_KEY"

    isolated_global.unlink()
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "other.example, Embeddings.Example")
    assert _write(tmp_path, REMOTE_TOML).embedding.base_url


def test_the_global_config_itself_is_not_subject_to_the_trust_check(isolated_global):
    isolated_global.parent.mkdir(parents=True)
    isolated_global.write_text(REMOTE_TOML)

    assert load_config(isolated_global).embedding.base_url == "https://embeddings.example/v1"


def test_plain_http_is_refused_for_remote_hosts_even_in_the_global_config(isolated_global):
    isolated_global.parent.mkdir(parents=True)
    isolated_global.write_text(REMOTE_TOML.replace("https://", "http://"))

    with pytest.raises(ConfigError, match="plain http"):
        load_config(isolated_global)


def test_plain_http_to_localhost_is_allowed_with_a_key(tmp_path, isolated_global):
    body = REMOTE_TOML.replace("https://embeddings.example", "http://localhost:8080")
    assert _write(tmp_path, body).embedding.base_url == "http://localhost:8080/v1"


def test_a_key_env_without_a_remote_url_is_not_a_destination(tmp_path, isolated_global):
    assert _write(tmp_path, '[embedding]\napi_key_env = "ANYTHING"\n').embedding.provider == "ollama"


def test_unreadable_global_config_still_yields_local_hosts(isolated_global):
    isolated_global.parent.mkdir(parents=True)
    isolated_global.write_text("not = [valid")
    assert trusted_hosts() == {"localhost", "127.0.0.1", "::1"}


UNSAFE_URLS = [
    "https://evil.example\\@trusted.example/v1",
    "https://evil.example\\.trusted.example/v1",
    "https://trusted.example\\@evil.example/v1",
    "https://user:pw@trusted.example/v1",
    "https://trusted.example:443@evil.example/v1",
    "https://trusted.example%2f@evil.example/v1",
    "https://trusted.example\t.evil.example/v1",
    "https://trusted.example\n.evil.example/v1",
    "https://trusted example/v1",
    "https://trusted。example/v1",
    "https://%74rusted.example/v1",
    "https://trusted.example\x00/v1",
    "https:///trusted.example/v1",
    "https://trüsted.example/v1",
]


@pytest.mark.parametrize("url", UNSAFE_URLS)
def test_urls_that_two_parsers_could_read_differently_never_get_a_key(url, tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "_GLOBAL_CONFIG", tmp_path / "global" / "recall.toml")
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "trusted.example")
    body = f'[embedding]\nprovider = "openai"\nmodel = "m"\nbase_url = {json.dumps(url)}\napi_key_env = "HOME"\n'

    with pytest.raises(ConfigError):
        _write(tmp_path, body)


@pytest.mark.parametrize("url", ["https://trusted.example/v1", "https://Trusted.Example:8443/v1/", "http://localhost:8080/v1", "http://[::1]:8080/v1"])
def test_plain_urls_on_trusted_or_local_hosts_are_accepted(url, tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "_GLOBAL_CONFIG", tmp_path / "global" / "recall.toml")
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "trusted.example")
    body = f'[embedding]\nprovider = "openai"\nmodel = "m"\nbase_url = "{url}"\napi_key_env = "HOME"\n'

    assert _write(tmp_path, body).embedding.base_url == url


@pytest.mark.parametrize("host", ["trusted.example/@evil.example", "trusted.example@evil.example", "evil.example\\@trusted.example", "tr usted.example"])
def test_qdrant_host_must_be_a_plain_hostname_when_a_key_is_sent(host, tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "_GLOBAL_CONFIG", tmp_path / "global" / "recall.toml")
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "trusted.example")
    body = f'[qdrant]\nhost = {json.dumps(host)}\nhttps = true\napi_key_env = "HOME"\n'

    with pytest.raises(ConfigError):
        _write(tmp_path, body)


def test_trusted_hosts_ignores_unsafe_urls_in_the_global_config(tmp_path, monkeypatch):
    global_cfg = tmp_path / "global" / "recall.toml"
    global_cfg.parent.mkdir(parents=True)
    global_cfg.write_text('[embedding]\nbase_url = "https://evil.example\\\\@trusted.example/v1"\n')
    monkeypatch.setattr(config_module, "_GLOBAL_CONFIG", global_cfg)
    monkeypatch.delenv("RECALL_TRUSTED_HOSTS", raising=False)

    assert trusted_hosts() == {"localhost", "127.0.0.1", "::1"}


from recall.config import DEFAULT_API_KEY_ENV, embedding_from_env, load_global_env


@pytest.fixture
def env_home(tmp_path, monkeypatch):
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    monkeypatch.setattr(config_module, "_GLOBAL_CONFIG", global_dir / "recall.toml")
    for name in list(__import__("os").environ):
        if name.startswith("RECALL_"):
            monkeypatch.delenv(name)
    return global_dir


def test_embedding_defaults_come_from_recall_env_variables(env_home, monkeypatch):
    monkeypatch.setenv("RECALL_EMBEDDING_BASE_URL", "https://embeddings.example/v1")
    monkeypatch.setenv("RECALL_EMBEDDING_MODEL", "some-model")
    monkeypatch.setenv("RECALL_EMBEDDING_BATCH_SIZE", "16")

    cfg = embedding_from_env()

    assert (cfg.provider, cfg.model, cfg.base_url, cfg.batch_size) == ("openai", "some-model", "https://embeddings.example/v1", 16)
    assert cfg.api_key_env == DEFAULT_API_KEY_ENV


def test_without_env_variables_the_defaults_are_local_ollama(env_home):
    cfg = embedding_from_env()
    assert (cfg.provider, cfg.base_url, cfg.api_key_env) == ("ollama", None, None)


def test_key_variable_name_and_provider_can_be_overridden(env_home, monkeypatch):
    monkeypatch.setenv("RECALL_EMBEDDING_BASE_URL", "https://embeddings.example/v1")
    monkeypatch.setenv("RECALL_EMBEDDING_API_KEY_ENV", "RECALL_MY_KEY")
    monkeypatch.setenv("RECALL_EMBEDDING_PROVIDER", "ollama")

    cfg = embedding_from_env()

    assert (cfg.provider, cfg.api_key_env) == ("ollama", "RECALL_MY_KEY")


def test_global_env_file_loads_only_recall_variables(env_home, monkeypatch):
    (env_home / ".env").write_text(
        "RECALL_EMBEDDING_BASE_URL=https://embeddings.example/v1\nCONFLUENCE_API_TOKEN=do-not-load\nRECALL_EMBEDDING_API_KEY=k\n"
    )
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)

    load_global_env()

    import os

    assert os.environ["RECALL_EMBEDDING_BASE_URL"] == "https://embeddings.example/v1"
    assert os.environ["RECALL_EMBEDDING_API_KEY"] == "k"
    assert "CONFLUENCE_API_TOKEN" not in os.environ
    for name in ("RECALL_EMBEDDING_BASE_URL", "RECALL_EMBEDDING_API_KEY"):
        monkeypatch.delenv(name)


def test_variables_already_in_the_environment_win_over_the_env_file(env_home, monkeypatch):
    (env_home / ".env").write_text("RECALL_EMBEDDING_MODEL=from-file\n")
    monkeypatch.setenv("RECALL_EMBEDDING_MODEL", "from-process")

    load_global_env()

    assert embedding_from_env().model == "from-process"


def test_a_dotenv_in_the_working_directory_is_never_read(env_home, tmp_path, monkeypatch):
    project = tmp_path / "hostile-repo"
    project.mkdir()
    (project / ".env").write_text("RECALL_EMBEDDING_BASE_URL=https://evil.example/v1\nRECALL_TRUSTED_HOSTS=evil.example\n")
    monkeypatch.chdir(project)

    load_global_env()

    import os

    assert "RECALL_EMBEDDING_BASE_URL" not in os.environ and "RECALL_TRUSTED_HOSTS" not in os.environ


def test_endpoint_from_the_global_env_file_is_trusted_for_local_recall_tomls(env_home, tmp_path, monkeypatch):
    (env_home / ".env").write_text("RECALL_EMBEDDING_BASE_URL=https://embeddings.example/v1\n")
    local = tmp_path / "project"
    local.mkdir()
    (local / "recall.toml").write_text('[embedding]\nprovider = "openai"\nmodel = "m"\n')

    cfg = load_config(local / "recall.toml")

    assert cfg.embedding.base_url == "https://embeddings.example/v1"
    assert cfg.embedding.api_key_env == DEFAULT_API_KEY_ENV
    assert "embeddings.example" in trusted_hosts()
    import os

    monkeypatch.delenv("RECALL_EMBEDDING_BASE_URL")


def test_local_recall_toml_cannot_redirect_the_env_configured_key_elsewhere(env_home, tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_EMBEDDING_BASE_URL", "https://embeddings.example/v1")
    (tmp_path / "recall.toml").write_text(
        '[embedding]\nprovider = "openai"\nbase_url = "https://evil.example/v1"\n'
    )

    with pytest.raises(ConfigError, match="untrusted host 'evil.example'"):
        load_config(tmp_path / "recall.toml")


def test_openai_provider_without_api_key_env_gets_the_default_name(env_home, tmp_path, monkeypatch):
    monkeypatch.setenv("RECALL_TRUSTED_HOSTS", "embeddings.example")
    (tmp_path / "recall.toml").write_text(
        '[embedding]\nprovider = "openai"\nmodel = "m"\nbase_url = "https://embeddings.example/v1"\n'
    )

    assert load_config(tmp_path / "recall.toml").embedding.api_key_env == DEFAULT_API_KEY_ENV


def test_repo_path_labels_are_parsed_and_forwarded_to_the_code_project(tmp_path):
    cfg = _write(
        tmp_path,
        '[[repos]]\nname = "iac"\nroot = "/iac"\npath_labels = ["{env}/{region}/service/{product}/{chart}/*"]\n\n'
        '[[repos]]\nname = "plain"\nroot = "/plain"\n',
    )
    iac, plain = cfg.repos
    assert iac.path_labels == ["{env}/{region}/service/{product}/{chart}/*"]
    assert iac.as_project().path_labels == iac.path_labels
    assert plain.path_labels == []
