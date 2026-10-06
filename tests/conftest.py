from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _never_touch_real_containers(monkeypatch):
    """Unit tests must not start containers or call systemd on the developer's machine."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"a test tried to run a real command: {args[0] if args else kwargs}")

    monkeypatch.setattr("recall.qdrant_service._default_run", refuse)
    monkeypatch.setattr("recall.commands.server._probe_mcp", refuse)


@pytest.fixture(autouse=True)
def _isolate_from_user_recall_config(monkeypatch, tmp_path_factory):
    """The developer's ~/.config/recall/{recall.toml,.env} must not leak into unit tests."""
    import os

    from recall import config as config_module

    monkeypatch.setattr(config_module, "_GLOBAL_CONFIG", tmp_path_factory.mktemp("noglobal") / "recall.toml")
    for key in [k for k in os.environ if k.startswith("RECALL_")]:
        monkeypatch.delenv(key)
