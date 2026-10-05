from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer

from recall.qdrant_guard import _can_autostart, _is_reachable, ensure_qdrant
from recall.qdrant_service import QdrantServiceError


def test_ensure_qdrant_does_nothing_when_already_reachable():
    with patch("recall.qdrant_guard._is_reachable", return_value=True), \
         patch("recall.qdrant_guard.QdrantService") as service:
        ensure_qdrant("http://localhost:6333")
    service.assert_not_called()


def test_ensure_qdrant_starts_the_local_service_when_not_reachable():
    with patch("recall.qdrant_guard._is_reachable", return_value=False), \
         patch("recall.qdrant_guard.QdrantService") as service:
        ensure_qdrant("http://localhost:6333")
    service.return_value.start.assert_called_once_with()


def test_ensure_qdrant_exits_with_the_service_error_message(capsys):
    with patch("recall.qdrant_guard._is_reachable", return_value=False), \
         patch("recall.qdrant_guard.QdrantService") as service:
        service.return_value.start.side_effect = QdrantServiceError("podman not found")
        with pytest.raises(typer.Exit):
            ensure_qdrant("http://localhost:6333")


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://localhost:6333", True),
        ("http://127.0.0.1:6333", True),
        ("http://localhost:16333", False),
        ("https://localhost:6333", False),
        ("http://qdrant.internal:6333", False),
        ("https://qdrant.internal:6333", False),
    ],
)
def test_can_autostart_only_for_the_local_plain_http_default_port(url, expected):
    assert _can_autostart(url) is expected


@pytest.mark.parametrize("url", ["https://qdrant.internal:6333", "http://localhost:16333"])
def test_ensure_qdrant_never_starts_anything_for_other_destinations(url):
    with patch("recall.qdrant_guard._is_reachable", return_value=False), \
         patch("recall.qdrant_guard.QdrantService") as service:
        with pytest.raises(typer.Exit):
            ensure_qdrant(url, "key")
    service.assert_not_called()


def test_is_reachable_sends_api_key_header():
    with patch("recall.qdrant_service.httpx.get") as get:
        get.return_value.status_code = 200
        assert _is_reachable("https://q:6333", "secret") is True
    assert get.call_args.kwargs["headers"] == {"api-key": "secret"}


def test_is_reachable_without_key_sends_no_header_and_is_false_on_errors():
    with patch("recall.qdrant_service.httpx.get") as get:
        get.return_value.status_code = 200
        _is_reachable("http://q:6333")
        assert get.call_args.kwargs["headers"] == {}
        get.side_effect = RuntimeError("down")
        assert _is_reachable("http://q:6333") is False
