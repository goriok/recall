from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class QdrantConfig:
    host: str = "localhost"
    port: int = 6333

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class EmbeddingConfig:
    model: str = "nomic-embed-text"
    provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"


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
]


@dataclass
class ProjectConfig:
    name: str
    path: str
    collection: str
    glob: str = "**/*.md"
    path_exclude: list[str] = field(default_factory=lambda: list(_DEFAULT_PATH_EXCLUDE))

    @property
    def resolved_path(self) -> Path:
        return Path(self.path).expanduser()


@dataclass
class SourceConfig:
    root: str
    glob: str = "**/*.md"
    exclude: list[str] = field(default_factory=list)
    path_exclude: list[str] = field(default_factory=lambda: list(_DEFAULT_PATH_EXCLUDE))

    @property
    def resolved_root(self) -> Path:
        return Path(self.root).expanduser()


@dataclass
class Config:
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    projects: list[ProjectConfig] = field(default_factory=list)
    sources: list[SourceConfig] = field(default_factory=list)

    def project(self, name: str) -> ProjectConfig:
        for p in self.all_projects():
            if p.name == name:
                return p
        raise ConfigError(f"unknown project '{name}' — check recall.toml")

    def discover_projects(self) -> list[ProjectConfig]:
        """Auto-discover projects from [[sources]] entries."""
        explicit_names = {p.name for p in self.projects}
        discovered: list[ProjectConfig] = []

        for source in self.sources:
            root = source.resolved_root
            if not root.exists():
                continue
            for subdir in sorted(root.iterdir()):
                if not subdir.is_dir():
                    continue
                if subdir.name in source.exclude:
                    continue
                if subdir.name in explicit_names:
                    continue
                # only include if there are matching files
                if not any(subdir.glob(source.glob)):
                    continue
                discovered.append(
                    ProjectConfig(
                        name=subdir.name,
                        path=str(subdir),
                        collection=subdir.name,
                        glob=source.glob,
                        path_exclude=list(source.path_exclude),
                    )
                )

        return discovered

    def all_projects(self) -> list[ProjectConfig]:
        """Explicit projects + auto-discovered, with explicit taking precedence."""
        explicit_names = {p.name for p in self.projects}
        discovered = [p for p in self.discover_projects() if p.name not in explicit_names]
        return self.projects + discovered


def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        raise ConfigError(f"recall.toml not found at {config_path}")

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    qdrant_data = data.get("qdrant", {})
    qdrant = QdrantConfig(
        host=qdrant_data.get("host", "localhost"),
        port=qdrant_data.get("port", 6333),
    )

    emb_data = data.get("embedding", {})
    embedding = EmbeddingConfig(
        model=emb_data.get("model", "nomic-embed-text"),
        provider=emb_data.get("provider", "ollama"),
        ollama_host=emb_data.get("ollama_host", "http://localhost:11434"),
    )

    projects = [
        ProjectConfig(
            name=p["name"],
            path=p["path"],
            collection=p["collection"],
            glob=p.get("glob", "**/*.md"),
            path_exclude=p.get("path_exclude", list(_DEFAULT_PATH_EXCLUDE)),
        )
        for p in data.get("projects", [])
    ]

    sources = [
        SourceConfig(
            root=s["root"],
            glob=s.get("glob", "**/*.md"),
            exclude=s.get("exclude", []),
            path_exclude=s.get("path_exclude", list(_DEFAULT_PATH_EXCLUDE)),
        )
        for s in data.get("sources", [])
    ]

    return Config(qdrant=qdrant, embedding=embedding, projects=projects, sources=sources)


_GLOBAL_CONFIG = Path.home() / ".config" / "recall" / "recall.toml"


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
