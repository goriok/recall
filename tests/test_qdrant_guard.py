import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from recall.qdrant_guard import ensure_qdrant, _is_reachable, _wait_until_ready

runner = CliRunner()


def test_ensure_qdrant_does_nothing_when_already_reachable():
    with patch("recall.qdrant_guard._is_reachable", return_value=True) as mock_check, \
         patch("recall.qdrant_guard.subprocess.run") as mock_run:
        ensure_qdrant("http://localhost:6333")
    mock_run.assert_not_called()


def test_ensure_qdrant_starts_docker_when_not_reachable(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  qdrant:\n    image: qdrant/qdrant\n")
    (tmp_path / "recall.toml").write_text("")

    with patch("recall.qdrant_guard._is_reachable", return_value=False), \
         patch("recall.qdrant_guard._find_compose_file", return_value=compose), \
         patch("recall.qdrant_guard._wait_until_ready", return_value=True), \
         patch("recall.qdrant_guard.subprocess.run") as mock_run:
        ensure_qdrant("http://localhost:6333")

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "podman" in args
    assert "up" in args


def test_ensure_qdrant_exits_when_compose_file_missing():
    import typer
    with patch("recall.qdrant_guard._is_reachable", return_value=False), \
         patch("recall.qdrant_guard._find_compose_file", return_value=None):
        with pytest.raises(Exception):  # typer.Exit raises click.exceptions.Exit
            ensure_qdrant("http://localhost:6333")


def test_ensure_qdrant_exits_when_qdrant_never_becomes_ready(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  qdrant:\n    image: qdrant/qdrant\n")

    with patch("recall.qdrant_guard._is_reachable", return_value=False), \
         patch("recall.qdrant_guard._find_compose_file", return_value=compose), \
         patch("recall.qdrant_guard.subprocess.run"), \
         patch("recall.qdrant_guard._wait_until_ready", return_value=False):
        with pytest.raises(Exception):  # typer.Exit raises click.exceptions.Exit
            ensure_qdrant("http://localhost:6333")


def test_is_reachable_returns_false_on_connection_error():
    with patch("recall.qdrant_guard.httpx.get", side_effect=Exception("refused")):
        assert _is_reachable("http://localhost:6333") is False


def test_wait_until_ready_returns_true_when_healthy():
    with patch("recall.qdrant_guard._is_reachable", return_value=True):
        assert _wait_until_ready("http://localhost:6333", timeout=2) is True


def test_wait_until_ready_returns_false_on_timeout():
    with patch("recall.qdrant_guard._is_reachable", return_value=False), \
         patch("recall.qdrant_guard.time.sleep"):
        assert _wait_until_ready("http://localhost:6333", timeout=1) is False
