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


@dataclass
class ProjectConfig:
    name: str
    path: str
    collection: str
    glob: str = "**/*.md"

    @property
    def resolved_path(self) -> Path:
        return Path(self.path).expanduser()


@dataclass
class Config:
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    projects: list[ProjectConfig] = field(default_factory=list)

    def project(self, name: str) -> ProjectConfig:
        for p in self.projects:
            if p.name == name:
                return p
        raise ConfigError(f"unknown project '{name}' — check recall.toml")


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
        )
        for p in data.get("projects", [])
    ]

    return Config(qdrant=qdrant, embedding=embedding, projects=projects)


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
