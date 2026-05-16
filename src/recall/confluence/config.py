from __future__ import annotations

import os
import tomllib
from pathlib import Path

from recall.confluence.client import ConfluenceConfig
from recall.config import ConfigError


def load_confluence_config(config_path: Path) -> ConfluenceConfig:
    """Load [confluence] section from recall.toml."""
    if not config_path.exists():
        raise ConfigError(f"recall.toml not found at {config_path}")

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    section = data.get("confluence")
    if not section:
        raise ConfigError(
            "No [confluence] section in recall.toml — add:\n\n"
            "[confluence]\n"
            'url = "https://myorg.atlassian.net"\n'
            'auth_type = "token"\n'
            'email = "user@org.com"\n'
            'token = "{env:CONFLUENCE_TOKEN}"\n'
        )

    token = _resolve_env(section.get("token", ""))
    email = _resolve_env(section.get("email", ""))

    return ConfluenceConfig(
        url=section["url"],
        auth_type=section.get("auth_type", "token"),
        token=token,
        email=email,
    )


def _resolve_env(value: str) -> str:
    """Resolve {env:VAR_NAME} placeholders from environment."""
    if value.startswith("{env:") and value.endswith("}"):
        var = value[5:-1]
        resolved = os.environ.get(var, "")
        if not resolved:
            raise ConfigError(f"Environment variable {var} is not set")
        return resolved
    return value
