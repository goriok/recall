from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values


class ConfigError(Exception):
    pass


_DEFAULT_QDRANT_PATH = str(Path.home() / ".local" / "share" / "recall" / "qdrant")
MAX_EMBEDDING_BATCH = 32
DEFAULT_API_KEY_ENV = "RECALL_EMBEDDING_API_KEY"
CODE_COLLECTION_PREFIX = "code."


@dataclass
class QdrantConfig:
    """Embedded (local) mode by default — path to an on-disk store, no server to run.

    Set `host`/`port` instead to talk to a real Qdrant server (needed for concurrent
    access from multiple processes at once — the embedded store takes an exclusive
    lock on `path` per process). `path` takes precedence when both are set.
    """

    path: str | None = _DEFAULT_QDRANT_PATH
    host: str | None = None
    port: int = 6333
    prefer_grpc: bool = False
    grpc_port: int = 6334
    https: bool = False
    api_key_env: str | None = None

    @property
    def url(self) -> str | None:
        if self.host is None:
            return None
        scheme = "https" if self.https else "http"
        return f"{scheme}://{self.host}:{self.port}"

    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env) or None


@dataclass
class EmbeddingConfig:
    model: str = "nomic-embed-text"
    provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    base_url: str | None = None
    api_key_env: str | None = None
    batch_size: int = MAX_EMBEDDING_BATCH
    max_chars: int = 1500


@dataclass
class GraphifyConfig:
    enabled: bool = True
    timeout_seconds: int = 300
    god_nodes_top: int = 10
    related_max: int = 10


_DEFAULT_PATH_EXCLUDE: list[str] = [
    "node_modules",
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".tox",
    ".eggs",
    ".opencode",
    ".claude",
    ".obsidian",
    "graphify-out",
    "target",
    "vendor",
]

_DEFAULT_DENY: list[str] = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_*",
    "*credentials*",
    "*secret*",
]

DEFAULT_MAX_FILE_BYTES = 524288
DEFAULT_MAX_CHUNK_CHARS = 4000


@dataclass
class ProjectConfig:
    name: str
    path: str
    collection: str
    glob: str = "**/*.md"
    path_exclude: list[str] = field(default_factory=lambda: list(_DEFAULT_PATH_EXCLUDE))
    kind: str = "docs"
    repo_name: str = ""
    repo_root: str | None = None
    globs: list[str] | None = None
    deny: list[str] = field(default_factory=lambda: list(_DEFAULT_DENY))
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    window_lines: int = 60
    window_overlap: int = 10
    graphify: GraphifyConfig = field(default_factory=GraphifyConfig)
    embedding: EmbeddingConfig | None = None

    @property
    def resolved_path(self) -> Path:
        return Path(self.path).expanduser()

    @property
    def resolved_repo_root(self) -> Path:
        return Path(self.repo_root).expanduser() if self.repo_root else self.resolved_path

    @property
    def effective_globs(self) -> list[str]:
        return self.globs if self.globs else [self.glob]

    @property
    def effective_repo_name(self) -> str:
        return self.repo_name or self.resolved_repo_root.name


@dataclass
class SourceConfig:
    root: str
    glob: str = "**/*.md"
    exclude: list[str] = field(default_factory=list)
    path_exclude: list[str] = field(default_factory=lambda: list(_DEFAULT_PATH_EXCLUDE))
    repo_root: str | None = None
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    embedding: EmbeddingConfig | None = None

    @property
    def resolved_root(self) -> Path:
        return Path(self.root).expanduser()

    @property
    def resolved_repo_root(self) -> Path:
        return Path(self.repo_root).expanduser() if self.repo_root else self.resolved_root.parent


@dataclass
class RepoConfig:
    name: str
    root: str
    globs: list[str] = field(default_factory=lambda: ["**/*.py", "**/*.md"])
    path_exclude: list[str] = field(default_factory=lambda: list(_DEFAULT_PATH_EXCLUDE))
    deny: list[str] = field(default_factory=lambda: list(_DEFAULT_DENY))
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    window_lines: int = 60
    window_overlap: int = 10
    graphify: GraphifyConfig = field(default_factory=GraphifyConfig)
    embedding: EmbeddingConfig | None = None

    @property
    def collection(self) -> str:
        return f"{CODE_COLLECTION_PREFIX}{self.name}"

    def as_project(self) -> ProjectConfig:
        return ProjectConfig(
            name=self.name,
            path=self.root,
            collection=self.collection,
            path_exclude=list(self.path_exclude),
            kind="code",
            repo_name=self.name,
            repo_root=self.root,
            globs=list(self.globs),
            deny=list(self.deny),
            max_chunk_chars=self.max_chunk_chars,
            max_file_bytes=self.max_file_bytes,
            window_lines=self.window_lines,
            window_overlap=self.window_overlap,
            graphify=self.graphify,
            embedding=self.embedding,
        )


@dataclass
class Config:
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    projects: list[ProjectConfig] = field(default_factory=list)
    sources: list[SourceConfig] = field(default_factory=list)
    repos: list[RepoConfig] = field(default_factory=list)

    def project(self, name: str) -> ProjectConfig:
        for p in self.all_projects():
            if p.name == name:
                return p
        raise ConfigError(f"unknown project '{name}' — check recall.toml")

    def project_for_collection(self, collection: str) -> ProjectConfig | None:
        for p in self.all_projects():
            if p.collection == collection or p.name == collection:
                return p
        return None

    def embedding_for(self, project: ProjectConfig | None) -> EmbeddingConfig:
        if project is not None and project.embedding is not None:
            return project.embedding
        return self.embedding

    def discover_projects(self) -> list[ProjectConfig]:
        """Auto-discover projects from [[sources]] entries.

        Collection names are prefixed with the source's repo dir name (e.g.
        my-ctx.auth) to avoid collisions when two repos have a topic
        with the same name.
        """
        explicit_names = {p.name for p in self.projects}
        discovered: list[ProjectConfig] = []

        for source in self.sources:
            root = source.resolved_root
            if not root.exists():
                continue
            prefix = root.parent.name
            repo_root = source.resolved_repo_root
            for subdir in sorted(root.iterdir()):
                if not subdir.is_dir():
                    continue
                if subdir.name in source.exclude:
                    continue
                name = f"{prefix}.{subdir.name}"
                if name in explicit_names:
                    continue
                if not any(subdir.glob(source.glob)):
                    continue
                discovered.append(
                    ProjectConfig(
                        name=name,
                        path=str(subdir),
                        collection=name,
                        glob=source.glob,
                        path_exclude=list(source.path_exclude),
                        repo_name=repo_root.name,
                        repo_root=str(repo_root),
                        max_chunk_chars=source.max_chunk_chars,
                        max_file_bytes=source.max_file_bytes,
                        embedding=source.embedding,
                    )
                )

        return discovered

    def all_projects(self) -> list[ProjectConfig]:
        """Explicit projects + auto-discovered + code repos, with explicit taking precedence."""
        explicit_names = {p.name for p in self.projects}
        discovered = [p for p in self.discover_projects() if p.name not in explicit_names]
        repos = [r.as_project() for r in self.repos if r.name not in explicit_names]
        return self.projects + discovered + repos

    def source_prefixes(self) -> set[str]:
        return {s.resolved_root.parent.name for s in self.sources}


def _parse_embedding(data: dict, base: EmbeddingConfig) -> EmbeddingConfig:
    batch_size = data.get("batch_size", base.batch_size)
    if not isinstance(batch_size, int) or not 1 <= batch_size <= MAX_EMBEDDING_BATCH:
        raise ConfigError(f"embedding.batch_size must be between 1 and {MAX_EMBEDDING_BATCH}")
    merged = replace(
        base,
        model=data.get("model", base.model),
        provider=data.get("provider", base.provider),
        ollama_host=data.get("ollama_host", base.ollama_host),
        base_url=data.get("base_url", base.base_url),
        api_key_env=data.get("api_key_env", base.api_key_env),
        batch_size=batch_size,
        max_chars=data.get("max_chars", base.max_chars),
    )
    if merged.provider == "openai" and merged.base_url and not merged.api_key_env:
        merged = replace(merged, api_key_env=DEFAULT_API_KEY_ENV)
    return merged


def _parse_graphify(data: dict | None) -> GraphifyConfig:
    data = data or {}
    base = GraphifyConfig()
    return GraphifyConfig(
        enabled=data.get("enabled", base.enabled),
        timeout_seconds=data.get("timeout_seconds", base.timeout_seconds),
        god_nodes_top=data.get("god_nodes_top", base.god_nodes_top),
        related_max=data.get("related_max", base.related_max),
    )


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_ENV_PREFIX = "RECALL_"
_GLOBAL_CONFIG = Path.home() / ".config" / "recall" / "recall.toml"


_HOST_RE = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


def load_global_env() -> None:
    """Load RECALL_* variables from ~/.config/recall/.env into the process environment.

    Only the global file is read — never a .env in the working directory, which belongs to
    whatever project is open — and only RECALL_* names, so unrelated secrets that happen to
    live in the same file never enter this process. Variables already set win.
    """
    path = _GLOBAL_CONFIG.parent / ".env"
    if not path.is_file():
        return
    for key, value in dotenv_values(path).items():
        if key.startswith(_ENV_PREFIX) and value is not None:
            os.environ.setdefault(key, value)


def embedding_from_env() -> EmbeddingConfig:
    """Embedding defaults taken from RECALL_EMBEDDING_* variables, so no endpoint has to live in a repo."""
    env = os.environ.get
    base_url = env("RECALL_EMBEDDING_BASE_URL") or None
    defaults = EmbeddingConfig()
    provider = env("RECALL_EMBEDDING_PROVIDER") or ("openai" if base_url else defaults.provider)
    batch = env("RECALL_EMBEDDING_BATCH_SIZE")
    return replace(
        defaults,
        provider=provider,
        model=env("RECALL_EMBEDDING_MODEL") or defaults.model,
        base_url=base_url,
        api_key_env=env("RECALL_EMBEDDING_API_KEY_ENV") or (DEFAULT_API_KEY_ENV if base_url else None),
        batch_size=int(batch) if batch and batch.isdigit() else defaults.batch_size,
    )


def _endpoint(url: str) -> tuple[str, str]:
    """Scheme and host of a URL that will receive an API key.

    The host is checked against an allowlist here but the connection is made by httpx, so
    anything the two parsers could read differently is refused: backslashes, userinfo,
    whitespace and control characters, non-ASCII or percent-encoded hosts.
    """
    if any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in url):
        raise ConfigError(f"unsafe characters in URL {url!r}")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if "@" in parsed.netloc or not (_HOST_RE.fullmatch(host) or host == "::1"):
        raise ConfigError(f"refusing URL with an unusual host: {url!r}")
    try:
        other = httpx.URL(url).host.lower().strip("[]")
    except httpx.InvalidURL:
        raise ConfigError(f"invalid URL {url!r}") from None
    if other != host:
        raise ConfigError(f"URL {url!r} is read as different hosts by different parsers — refusing it")
    return parsed.scheme, host


def _hostname(url: str) -> str:
    try:
        return _endpoint(url)[1]
    except ConfigError:
        return ""


def trusted_endpoints() -> dict[str, set[str] | None]:
    """Remote hosts a project-local recall.toml may talk to, with the env vars it may send them.

    A project-local recall.toml is untrusted input: without this check it could send the
    indexed content, or any environment variable named in api_key_env, to a host of its
    choosing. A value of None means any variable; a set pins the variables the global
    recall.toml itself pairs with that host.
    """
    endpoints: dict[str, set[str] | None] = {host: None for host in _LOCAL_HOSTS}
    for host in os.environ.get("RECALL_TRUSTED_HOSTS", "").split(","):
        if host.strip():
            endpoints[host.strip().lower()] = None
    env_embedding = embedding_from_env()
    if env_embedding.base_url:
        host = _hostname(env_embedding.base_url)
        if host and host not in endpoints:
            endpoints[host] = {env_embedding.api_key_env} if env_embedding.api_key_env else set()
    if not _GLOBAL_CONFIG.exists():
        return endpoints
    try:
        data = tomllib.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return endpoints

    def allow(host: str, key_env: str | None) -> None:
        if not host or (host in endpoints and endpoints[host] is None):
            return
        endpoints.setdefault(host, set())
        if key_env:
            endpoints[host].add(key_env)

    tables = [data.get("embedding", {})]
    for key in ("projects", "sources", "repos"):
        tables += [entry.get("embedding", {}) for entry in data.get(key, [])]
    for table in tables:
        if table.get("base_url"):
            allow(_hostname(table["base_url"]), table.get("api_key_env"))
        if table.get("ollama_host"):
            allow(_hostname(table["ollama_host"]), None)
    qdrant = data.get("qdrant", {})
    if qdrant.get("host"):
        allow(str(qdrant["host"]).lower(), qdrant.get("api_key_env"))
    for host in data.get("security", {}).get("trusted_hosts", []):
        endpoints[str(host).lower()] = None
    return endpoints


def trusted_hosts() -> set[str]:
    return set(trusted_endpoints())


def _guard_destination(
    what: str, url: str, key_env: str | None, trusted: dict[str, set[str] | None] | None
) -> None:
    scheme, host = _endpoint(url)
    if key_env and scheme != "https" and host not in _LOCAL_HOSTS:
        raise ConfigError(f"{what}: refusing to send ${key_env} to {host} over plain http — use https")
    if trusted is None or host in _LOCAL_HOSTS:
        return
    if host not in trusted:
        raise ConfigError(
            f"{what}: refusing to talk to untrusted host '{host}' — this recall.toml is not the global one; "
            f"declare the host in ~/.config/recall/recall.toml, in its [security] trusted_hosts, or in RECALL_TRUSTED_HOSTS"
        )
    allowed = trusted[host]
    if key_env and allowed is not None and key_env not in allowed:
        raise ConfigError(
            f"{what}: ${key_env} is not authorized for '{host}' — the global recall.toml pairs that host "
            f"with {sorted(allowed) or 'no key'}"
        )


def _guard_embedding(cfg: EmbeddingConfig | None, trusted: dict[str, set[str] | None] | None) -> None:
    if cfg is None:
        return
    if cfg.provider == "openai" and cfg.base_url:
        _guard_destination("embedding", cfg.base_url, cfg.api_key_env, trusted)
    elif cfg.provider == "ollama":
        _guard_destination("embedding", cfg.ollama_host, None, trusted)


def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        raise ConfigError(f"recall.toml not found at {config_path}")
    load_global_env()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    is_global = config_path.resolve() == _GLOBAL_CONFIG.resolve()
    trusted = None if is_global else trusted_endpoints()

    qdrant_data = data.get("qdrant", {})
    extras = {
        "prefer_grpc": qdrant_data.get("prefer_grpc", False),
        "grpc_port": qdrant_data.get("grpc_port", 6334),
        "https": qdrant_data.get("https", False),
        "api_key_env": qdrant_data.get("api_key_env"),
    }
    if "host" in qdrant_data:
        qdrant = QdrantConfig(
            path=qdrant_data.get("path"),
            host=qdrant_data["host"],
            port=qdrant_data.get("port", 6333),
            **extras,
        )
    else:
        qdrant = QdrantConfig(path=qdrant_data.get("path", _DEFAULT_QDRANT_PATH), **extras)

    if qdrant.host is not None:
        if _endpoint(qdrant.url)[1] != qdrant.host.lower():
            raise ConfigError(f"qdrant.host {qdrant.host!r} is not a plain hostname")
        _guard_destination("qdrant", qdrant.url, qdrant.api_key_env, trusted)

    embedding = _parse_embedding(data.get("embedding", {}), embedding_from_env())
    _guard_embedding(embedding, trusted)

    def override(entry: dict) -> EmbeddingConfig | None:
        table = entry.get("embedding")
        if not table:
            return None
        parsed = _parse_embedding(table, embedding)
        _guard_embedding(parsed, trusted)
        return parsed

    projects = [
        ProjectConfig(
            name=p["name"],
            path=p["path"],
            collection=p["collection"],
            glob=p.get("glob", "**/*.md"),
            path_exclude=p.get("path_exclude", list(_DEFAULT_PATH_EXCLUDE)),
            max_chunk_chars=p.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS),
            max_file_bytes=p.get("max_file_bytes", DEFAULT_MAX_FILE_BYTES),
            embedding=override(p),
        )
        for p in data.get("projects", [])
    ]

    sources = [
        SourceConfig(
            root=s["root"],
            glob=s.get("glob", "**/*.md"),
            exclude=s.get("exclude", []),
            path_exclude=s.get("path_exclude", list(_DEFAULT_PATH_EXCLUDE)),
            repo_root=s.get("repo_root"),
            max_chunk_chars=s.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS),
            max_file_bytes=s.get("max_file_bytes", DEFAULT_MAX_FILE_BYTES),
            embedding=override(s),
        )
        for s in data.get("sources", [])
    ]

    repos = [
        RepoConfig(
            name=r.get("name") or Path(r["root"]).expanduser().name,
            root=r["root"],
            globs=r.get("globs", ["**/*.py", "**/*.md"]),
            path_exclude=r.get("path_exclude", list(_DEFAULT_PATH_EXCLUDE)),
            deny=r.get("deny", list(_DEFAULT_DENY)),
            max_chunk_chars=r.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS),
            max_file_bytes=r.get("max_file_bytes", DEFAULT_MAX_FILE_BYTES),
            window_lines=r.get("window_lines", 60),
            window_overlap=r.get("window_overlap", 10),
            graphify=_parse_graphify(r.get("graphify")),
            embedding=override(r),
        )
        for r in data.get("repos", [])
    ]

    return Config(
        qdrant=qdrant, embedding=embedding, projects=projects, sources=sources, repos=repos
    )


def find_config() -> Path:
    """Walk up from CWD looking for recall.toml, then fall back to ~/.config/recall/recall.toml."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        candidate = directory / "recall.toml"
        if candidate.exists():
            return candidate
    if _GLOBAL_CONFIG.exists():
        return _GLOBAL_CONFIG
    raise ConfigError(
        "recall.toml not found — run from inside a recall project, "
        "or place a global config at ~/.config/recall/recall.toml"
    )
