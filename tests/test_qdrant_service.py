from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from recall.qdrant_service import (
    LEGACY_CONTAINER,
    QdrantService,
    QdrantServiceError,
    ServiceSpec,
)

PODMAN = "/opt/bin/podman"


class FakeHost:
    """A scripted podman/systemctl/loginctl: records every command and answers from a table."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.container = "absent"
        self.legacy = "absent"
        self.linger = "Linger=yes"
        self.unit_enabled = "disabled"
        self.unit_active = "inactive"
        self.run_error = ""
        self.fail: set[str] = set()

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        text = " ".join(cmd)
        out, code = "", 0
        if cmd[0] == PODMAN and cmd[1:3] == ["container", "inspect"]:
            state = self.legacy if cmd[3] == LEGACY_CONTAINER else self.container
            out, code = ("", 1) if state == "absent" else (state + "\n", 0)
        elif cmd[0] == PODMAN and cmd[1] == "run":
            if self.run_error:
                return subprocess.CompletedProcess(cmd, 126, "", self.run_error)
            self.container = "running"
        elif cmd[0] == PODMAN and cmd[1] == "start":
            self.container = "running"
        elif cmd[0] == PODMAN and cmd[1] == "stop":
            self.container = "exited"
        elif cmd[0] == PODMAN and cmd[1] == "rm":
            self.container = "absent"
        elif cmd[0] == "loginctl" and cmd[1] == "show-user":
            out = self.linger + "\n"
        elif cmd[0] == "loginctl" and cmd[1] == "enable-linger":
            self.linger = "Linger=yes"
        elif cmd[:2] == ["systemctl", "--user"]:
            verb = cmd[2]
            if verb == "is-enabled":
                out = self.unit_enabled + "\n"
            elif verb == "is-active":
                out = self.unit_active + "\n"
            elif verb in ("enable", "start", "restart"):
                self.unit_enabled = "enabled" if verb == "enable" else self.unit_enabled
                self.unit_active = "active"
                self.container = "running"
            elif verb == "stop":
                self.unit_active, self.container = "inactive", "exited"
            elif verb == "disable":
                self.unit_enabled, self.unit_active = "disabled", "inactive"
        if any(f in text for f in self.fail):
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        return subprocess.CompletedProcess(cmd, code, out, "")

    def ran(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]


@pytest.fixture
def host():
    return FakeHost()


def _service(host, tmp_path, healthy=lambda url: True, which=None, spec=None):
    which = which or (lambda name: f"/opt/bin/{name}")
    state = {"healthy": healthy}
    service = QdrantService(
        spec or ServiceSpec(), run=host, which=which, healthy=lambda url: state["healthy"](url),
        sleep=lambda s: None, config_home=tmp_path,
    )
    service.state = state
    return service


def test_start_is_a_noop_when_qdrant_already_answers(host, tmp_path):
    assert _service(host, tmp_path).start() == "already-running"
    assert host.calls == []


def test_start_creates_a_loopback_only_container_with_a_restart_policy(host, tmp_path):
    service = _service(host, tmp_path)
    answers = iter([False, False, True])
    service.state["healthy"] = lambda url: next(answers)

    assert service.start() == "container"

    [run] = host.ran(PODMAN, "run")
    assert run[2:5] == ["-d", "--restart", "unless-stopped"]
    assert "127.0.0.1:6333:6333" in run and "127.0.0.1:6334:6334" in run
    assert "recall_qdrant_data:/qdrant/storage" in run
    assert not any(a.startswith("0.0.0.0") or a == "6333:6333" for a in run)


def test_start_restarts_an_existing_stopped_container_instead_of_creating_another(host, tmp_path):
    host.container = "exited"
    service = _service(host, tmp_path)
    answers = iter([False, True])
    service.state["healthy"] = lambda url: next(answers)

    assert service.start() == "container"

    assert host.ran(PODMAN, "start") and not host.ran(PODMAN, "run")


def test_start_goes_through_systemd_when_the_unit_is_installed(host, tmp_path):
    service = _service(host, tmp_path)
    service.unit_path.parent.mkdir(parents=True)
    service.unit_path.write_text("[Unit]\n")
    answers = iter([False, True])
    service.state["healthy"] = lambda url: next(answers)

    assert service.start() == "service"

    assert host.ran("systemctl", "--user", "start", "recall-qdrant.service")
    assert not host.ran(PODMAN, "run")


def test_start_reports_a_port_conflict_naming_the_old_compose_container(host, tmp_path):
    host.legacy = "running"
    host.run_error = "Error: rootlessport listen tcp 127.0.0.1:6333: bind: address already in use"
    service = _service(host, tmp_path, healthy=lambda url: False)

    with pytest.raises(QdrantServiceError, match=r"already in use.*recall_qdrant_1.*podman rm -f recall_qdrant_1"):
        service.start()


def test_start_fails_with_a_clear_message_when_podman_is_missing(host, tmp_path):
    service = _service(host, tmp_path, healthy=lambda url: False, which=lambda name: None)
    with pytest.raises(QdrantServiceError, match="podman not found"):
        service.start()


def test_start_fails_when_qdrant_never_answers(host, tmp_path, monkeypatch):
    monkeypatch.setattr("recall.qdrant_service.START_TIMEOUT", 0)
    service = _service(host, tmp_path, healthy=lambda url: False)
    with pytest.raises(QdrantServiceError, match="did not answer"):
        service.start()


def test_unit_file_supervises_a_foreground_podman_run_and_restarts_it(host, tmp_path):
    text = _service(host, tmp_path).unit_text()

    assert f"ExecStart={PODMAN} run --rm --replace --name recall-qdrant" in text
    assert "-p 127.0.0.1:6333:6333" in text and "-p 127.0.0.1:6334:6334" in text
    assert "-v recall_qdrant_data:/qdrant/storage" in text
    assert f"ExecStop={PODMAN} stop -t 10 recall-qdrant" in text
    assert "Restart=always" in text and "WantedBy=default.target" in text
    assert "Environment=PATH=/opt/bin:" in text
    assert " -d " not in text


def test_enable_installs_the_unit_reloads_enables_and_turns_on_lingering(host, tmp_path):
    host.linger = "Linger=no"
    service = _service(host, tmp_path)

    notes = service.enable()

    assert service.unit_path.read_text() == service.unit_text()
    order = [" ".join(c) for c in host.calls if c[0] in ("systemctl", "loginctl") and c[1] != "show-user"]
    assert order == [
        "systemctl --user daemon-reload",
        "systemctl --user enable --now recall-qdrant.service",
        "loginctl enable-linger " + __import__("os").environ.get("USER", ""),
    ]
    assert any("lingering" in n for n in notes)


def test_enable_without_linger_only_warns(host, tmp_path):
    host.linger = "Linger=no"
    notes = _service(host, tmp_path).enable(linger=False)
    assert not host.ran("loginctl", "enable-linger")
    assert any("starts when you log in" in n for n in notes)


def test_enable_leaves_lingering_alone_when_it_is_already_on(host, tmp_path):
    _service(host, tmp_path).enable()
    assert not host.ran("loginctl", "enable-linger")


def test_enable_replaces_a_standalone_container_so_the_unit_owns_the_name(host, tmp_path):
    host.container = "running"
    notes = _service(host, tmp_path).enable()
    assert host.ran(PODMAN, "rm", "-f", "recall-qdrant")
    assert any("removed the standalone container" in n for n in notes)


def test_enable_refuses_while_the_old_compose_container_holds_the_ports(host, tmp_path):
    host.legacy = "running"
    service = _service(host, tmp_path)
    with pytest.raises(QdrantServiceError, match="podman rm -f recall_qdrant_1"):
        service.enable()
    assert not service.unit_path.exists()


def test_enable_fails_without_systemd(host, tmp_path):
    service = _service(host, tmp_path, which=lambda n: None if n == "systemctl" else f"/opt/bin/{n}")
    with pytest.raises(QdrantServiceError, match="systemctl not found"):
        service.enable()


def test_enable_surfaces_a_systemctl_failure(host, tmp_path):
    host.fail = {"enable --now"}
    with pytest.raises(QdrantServiceError, match="boom"):
        _service(host, tmp_path).enable()


def test_disable_removes_the_unit_and_keeps_the_data(host, tmp_path):
    service = _service(host, tmp_path)
    service.enable()

    notes = service.disable()

    assert not service.unit_path.exists()
    assert host.ran("systemctl", "--user", "disable", "--now", "recall-qdrant.service")
    assert any("data kept in volume recall_qdrant_data" in n for n in notes)
    assert not host.ran(PODMAN, "volume")


def test_disable_when_autostart_was_never_enabled_is_harmless(host, tmp_path):
    assert _service(host, tmp_path).disable() == ["autostart was not enabled"]
    assert host.calls == []


def test_stop_uses_systemd_when_the_unit_exists_otherwise_podman(host, tmp_path):
    plain = _service(host, tmp_path)
    host.container = "running"
    assert plain.stop() == "container"
    assert host.ran(PODMAN, "stop", "-t", "10", "recall-qdrant")
    assert plain.stop() == "not-running"

    managed = _service(host, tmp_path)
    managed.enable()
    assert managed.stop() == "service"
    assert host.ran("systemctl", "--user", "stop", "recall-qdrant.service")


def test_restart_for_a_managed_service_waits_until_it_answers(host, tmp_path):
    service = _service(host, tmp_path)
    service.enable()
    assert service.restart() == "service"
    assert host.ran("systemctl", "--user", "restart", "recall-qdrant.service")


def test_restart_for_a_plain_container_is_stop_then_start(host, tmp_path):
    host.container = "running"
    service = _service(host, tmp_path)
    answers = iter([False, True])
    service.state["healthy"] = lambda url: next(answers)
    assert service.restart() == "container"
    assert host.ran(PODMAN, "stop") and host.ran(PODMAN, "start")


def test_status_reports_reachability_autostart_lingering_and_the_legacy_container(host, tmp_path):
    service = _service(host, tmp_path)
    service.enable()
    host.unit_enabled, host.unit_active = "enabled", "active"
    host.legacy = "running"

    status = service.status()

    assert status.reachable and status.autostart_enabled and status.autostart_active
    assert status.linger is True and status.legacy_container == "running"
    assert status.container == "running"


def test_status_without_podman_or_loginctl_degrades(host, tmp_path):
    service = _service(host, tmp_path, which=lambda n: None)
    status = service.status()
    assert status.container == "podman-missing" and status.linger is None and status.legacy_container == ""


def test_a_custom_spec_changes_name_ports_and_volume(host, tmp_path):
    spec = ServiceSpec(name="recall-qdrant-test", volume="test_data", http_port=16333, grpc_port=16334)
    text = _service(host, tmp_path, spec=spec).unit_text()
    assert "--name recall-qdrant-test" in text and "127.0.0.1:16333:6333" in text and "-v test_data:" in text
    assert spec.unit == "recall-qdrant-test.service" and spec.url == "http://localhost:16333"


def test_logs_pass_tail_and_follow_to_podman(host, tmp_path):
    service = _service(host, tmp_path)
    assert service.logs(tail=5, follow=True) == 0
    assert host.calls[-1] == [PODMAN, "logs", "--tail=5", "-f", "recall-qdrant"]


def test_default_executor_is_the_conftest_trap():
    from recall.qdrant_service import QdrantService as Real

    with pytest.raises(AssertionError, match="real command"):
        Real(which=lambda n: "/x/" + n, healthy=lambda u: False, config_home=Path("/nonexistent")).start()
