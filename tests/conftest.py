from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _never_touch_real_containers(monkeypatch):
    """Unit tests must not start containers or call systemd on the developer's machine."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"a test tried to run a real command: {args[0] if args else kwargs}")

    monkeypatch.setattr("recall.qdrant_service._default_run", refuse)
    monkeypatch.setattr("recall.commands.server._probe_mcp", refuse)
