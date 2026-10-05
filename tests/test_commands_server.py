from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from recall.cli import app
from recall.qdrant_service import QdrantServiceError, ServiceSpec, Status

runner = CliRunner()


def _service(**overrides):
    service = MagicMock()
    service.spec = ServiceSpec()
    service.autostart_installed.return_value = overrides.pop("installed", False)
    for name, value in overrides.items():
        getattr(service, name).return_value = value
    return service


def _invoke(service, *args):
    with patch("recall.commands.server._service", return_value=service):
        return runner.invoke(app, ["server", *args])


def test_start_reports_ready_and_suggests_enable_when_not_persistent():
    result = _invoke(_service(start="container"), "start")
    assert result.exit_code == 0
    assert "Qdrant ready at http://localhost:6333 (container)" in result.output
    assert "recall server enable" in result.output


def test_start_does_not_nag_when_autostart_is_installed():
    result = _invoke(_service(start="service", installed=True), "start")
    assert "recall server enable" not in result.output


def test_start_when_already_running_says_so():
    result = _invoke(_service(start="already-running"), "start")
    assert result.exit_code == 0 and "already running" in result.output


def test_start_failure_prints_the_reason_and_exits_nonzero():
    service = _service()
    service.start.side_effect = QdrantServiceError("port 6333 is already in use")
    result = _invoke(service, "start")
    assert result.exit_code == 1 and "port 6333 is already in use" in result.output


@pytest.mark.parametrize(
    "how,expected",
    [("container", "Qdrant stopped"), ("not-running", "was not running"), ("service", "comes back at the next boot")],
)
def test_stop_messages(how, expected):
    result = _invoke(_service(stop=how), "stop")
    assert result.exit_code == 0 and expected in result.output


def test_restart_and_its_failure():
    assert "restarted" in _invoke(_service(restart="service"), "restart").output
    service = _service()
    service.restart.side_effect = QdrantServiceError("nope")
    assert _invoke(service, "restart").exit_code == 1


def test_enable_prints_each_note_and_passes_the_linger_flag():
    service = _service(enable=["wrote /x.service", "enabled and started"])
    result = _invoke(service, "enable", "--no-linger")
    assert result.exit_code == 0 and "wrote /x.service" in result.output
    service.enable.assert_called_once_with(linger=False)


def test_enable_failure_exits_nonzero_with_the_reason():
    service = _service()
    service.enable.side_effect = QdrantServiceError("remove it first: podman rm -f recall_qdrant_1")
    result = _invoke(service, "enable")
    assert result.exit_code == 1 and "podman rm -f recall_qdrant_1" in result.output


def test_disable_prints_notes_and_handles_errors():
    assert "disabled" in _invoke(_service(disable=["disabled and removed x"]), "disable").output
    service = _service()
    service.disable.side_effect = QdrantServiceError("systemctl not found")
    assert _invoke(service, "disable").exit_code == 1


def test_status_shows_everything_and_flags_the_legacy_container():
    status = Status(reachable=True, container="running", autostart_enabled=True, autostart_active=True, linger=True, legacy_container="running")
    service = _service(status=status, installed=True)
    with patch("recall.commands.server._probe_mcp", return_value="0.5.0"):
        result = _invoke(service, "status")
    assert "Qdrant reachable" in result.output
    assert "autostart: enabled=True (active), lingering=True" in result.output
    assert "old compose container recall_qdrant_1 is running" in result.output
    assert "recall-mcp v0.5.0" in result.output


def test_status_when_down_and_autostart_off():
    status = Status(reachable=False, container="absent", autostart_enabled=False, autostart_active=False, linger=None, legacy_container="")
    with patch("recall.commands.server._probe_mcp", side_effect=RuntimeError("no binary")):
        result = _invoke(_service(status=status), "status")
    assert "Qdrant unreachable" in result.output and "autostart: off" in result.output
    assert "recall-mcp not responding: no binary" in result.output


def test_status_surfaces_a_service_error():
    service = _service()
    service.status.side_effect = QdrantServiceError("podman exploded")
    assert _invoke(service, "status").exit_code == 1


def test_logs_pass_through_and_propagate_failures():
    service = _service(logs=0)
    assert _invoke(service, "logs", "--tail", "7", "-f").exit_code == 0
    service.logs.assert_called_once_with(tail=7, follow=True)
    assert _invoke(_service(logs=3), "logs").exit_code == 3


def test_mcp_initialize_probe_reads_the_version_and_sends_a_jsonrpc_initialize():
    from recall.commands import server

    reply = '{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"version":"9.9"}}}\n'
    with patch.object(server.subprocess, "run", return_value=MagicMock(stdout=reply)) as run:
        assert server._run_mcp_initialize() == "9.9"
    assert '"method": "initialize"' in run.call_args.kwargs["input"]
    assert run.call_args.kwargs["timeout"] == 5
