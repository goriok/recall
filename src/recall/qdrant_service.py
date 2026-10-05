from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

DEFAULT_IMAGE = "docker.io/qdrant/qdrant:latest"
LEGACY_CONTAINER = "recall_qdrant_1"
START_TIMEOUT = 60


class QdrantServiceError(Exception):
    pass


def _default_run(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(*args, **kwargs)


@dataclass(frozen=True)
class ServiceSpec:
    name: str = "recall-qdrant"
    volume: str = "recall_qdrant_data"
    image: str = DEFAULT_IMAGE
    http_port: int = 6333
    grpc_port: int = 6334

    @property
    def unit(self) -> str:
        return f"{self.name}.service"

    @property
    def url(self) -> str:
        return f"http://localhost:{self.http_port}"


@dataclass
class Status:
    reachable: bool
    container: str
    autostart_enabled: bool
    autostart_active: bool
    linger: bool | None
    legacy_container: str


def is_healthy(url: str, api_key: str | None = None) -> bool:
    headers = {"api-key": api_key} if api_key else {}
    try:
        return httpx.get(f"{url}/healthz", headers=headers, timeout=2.0).status_code == 200
    except Exception:
        return False


class QdrantService:
    """A local Qdrant container: started on demand and, optionally, supervised by a systemd user unit.

    The container publishes only on 127.0.0.1 — Qdrant has no authentication unless an API
    key is configured, so it must not listen on the network.
    """

    def __init__(
        self,
        spec: ServiceSpec = ServiceSpec(),
        *,
        run: Callable[..., subprocess.CompletedProcess] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        healthy: Callable[[str], bool] = is_healthy,
        sleep: Callable[[float], None] = time.sleep,
        config_home: Path | None = None,
    ) -> None:
        self.spec = spec
        self._run = run or _default_run
        self._which = which
        self._healthy = healthy
        self._sleep = sleep
        self._config_home = config_home or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    @property
    def unit_path(self) -> Path:
        return self._config_home / "systemd" / "user" / self.spec.unit

    def _podman(self) -> str:
        path = self._which("podman")
        if not path:
            raise QdrantServiceError("podman not found — install Podman, or run Qdrant yourself and point [qdrant] at it")
        return path

    def _exec(self, *cmd: str, check: bool = False) -> subprocess.CompletedProcess:
        result = self._run(list(cmd), capture_output=True, text=True)
        if check and result.returncode != 0:
            raise QdrantServiceError((result.stderr or result.stdout or "command failed").strip())
        return result

    def _systemctl(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        if not self._which("systemctl"):
            raise QdrantServiceError("systemctl not found — the boot-time service needs a Linux systemd user session")
        return self._exec("systemctl", "--user", *args, check=check)

    def _podman_run_args(self) -> list[str]:
        s = self.spec
        return [
            "--name", s.name,
            "-p", f"127.0.0.1:{s.http_port}:6333",
            "-p", f"127.0.0.1:{s.grpc_port}:6334",
            "-v", f"{s.volume}:/qdrant/storage",
            s.image,
        ]

    def unit_text(self) -> str:
        podman = self._podman()
        s = self.spec
        run_args = " ".join(["--rm", "--replace", *self._podman_run_args()])
        return (
            "[Unit]\n"
            "Description=Qdrant vector store for recall\n"
            "Wants=network-online.target\n"
            "After=network-online.target\n"
            "\n"
            "[Service]\n"
            f"Environment=PATH={Path(podman).parent}:/usr/local/bin:/usr/bin:/bin\n"
            f"ExecStart={podman} run {run_args}\n"
            f"ExecStop={podman} stop -t 10 {s.name}\n"
            "Restart=always\n"
            "RestartSec=5\n"
            "TimeoutStartSec=600\n"
            "TimeoutStopSec=30\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def autostart_installed(self) -> bool:
        return self.unit_path.exists()

    def _linger(self) -> bool | None:
        if not self._which("loginctl"):
            return None
        result = self._exec("loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger")
        if result.returncode != 0:
            return None
        return result.stdout.strip().endswith("=yes")

    def _container_state(self) -> str:
        result = self._exec(self._podman(), "container", "inspect", self.spec.name, "--format", "{{.State.Status}}")
        return result.stdout.strip() if result.returncode == 0 else "absent"

    def _legacy_running(self) -> bool:
        result = self._exec(self._podman(), "container", "inspect", LEGACY_CONTAINER, "--format", "{{.State.Status}}")
        return result.returncode == 0 and result.stdout.strip() == "running"

    def _wait_healthy(self) -> None:
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if self._healthy(self.spec.url):
                return
            self._sleep(0.5)
        raise QdrantServiceError(f"Qdrant started but did not answer at {self.spec.url} within {START_TIMEOUT}s")

    def start(self) -> str:
        """Make Qdrant reachable. Returns how: 'already-running', 'service' or 'container'."""
        if self._healthy(self.spec.url):
            return "already-running"
        if self.autostart_installed():
            self._systemctl("start", self.spec.unit, check=True)
            how = "service"
        else:
            podman = self._podman()
            if self._container_state() == "absent":
                result = self._exec(podman, "run", "-d", "--restart", "unless-stopped", *self._podman_run_args())
            else:
                result = self._exec(podman, "start", self.spec.name)
            if result.returncode != 0:
                raise QdrantServiceError(self._explain(result.stderr or result.stdout))
            how = "container"
        self._wait_healthy()
        return how

    def _explain(self, message: str) -> str:
        message = message.strip()
        if "address already in use" in message or "bind" in message:
            holder = ""
            if self._legacy_running():
                holder = f" (the old compose container '{LEGACY_CONTAINER}' is running — stop it with: podman rm -f {LEGACY_CONTAINER})"
            return f"port {self.spec.http_port} or {self.spec.grpc_port} is already in use{holder}: {message}"
        return message or "could not start the Qdrant container"

    def stop(self) -> str:
        """Stop Qdrant. Returns 'service', 'container' or 'not-running'."""
        if self.autostart_installed():
            self._systemctl("stop", self.spec.unit, check=True)
            return "service"
        if self._container_state() in ("absent", "exited", "stopped", "created"):
            return "not-running"
        self._exec(self._podman(), "stop", "-t", "10", self.spec.name, check=True)
        return "container"

    def restart(self) -> str:
        if self.autostart_installed():
            self._systemctl("restart", self.spec.unit, check=True)
            self._wait_healthy()
            return "service"
        self.stop()
        return self.start()

    def enable(self, *, linger: bool = True) -> list[str]:
        """Install and start the systemd user unit so Qdrant returns after a reboot."""
        if self._legacy_running():
            raise QdrantServiceError(
                f"the old compose container '{LEGACY_CONTAINER}' holds the ports — "
                f"remove it first (your data stays in volume {self.spec.volume}): podman rm -f {LEGACY_CONTAINER}"
            )
        podman = self._podman()
        notes: list[str] = []
        if self._container_state() != "absent":
            self._exec(podman, "rm", "-f", self.spec.name)
            notes.append(f"removed the standalone container '{self.spec.name}' so the unit can own it")
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text(self.unit_text(), encoding="utf-8")
        notes.append(f"wrote {self.unit_path}")
        self._systemctl("daemon-reload", check=True)
        self._systemctl("enable", "--now", self.spec.unit, check=True)
        notes.append(f"enabled and started {self.spec.unit}")
        current = self._linger()
        if linger and current is False:
            self._exec("loginctl", "enable-linger", os.environ.get("USER", ""), check=True)
            notes.append("enabled lingering: the user service now starts at boot, before you log in")
        elif current is False:
            notes.append("lingering is off: the service starts when you log in, not at boot")
        self._wait_healthy()
        return notes

    def disable(self) -> list[str]:
        """Remove the systemd user unit. The data volume and lingering are left alone."""
        if not self.autostart_installed():
            return ["autostart was not enabled"]
        self._systemctl("disable", "--now", self.spec.unit)
        self.unit_path.unlink()
        self._systemctl("daemon-reload", check=True)
        return [f"disabled and removed {self.spec.unit}", f"data kept in volume {self.spec.volume}"]

    def status(self) -> Status:
        enabled = active = False
        if self.autostart_installed():
            enabled = self._systemctl("is-enabled", self.spec.unit).stdout.strip() == "enabled"
            active = self._systemctl("is-active", self.spec.unit).stdout.strip() == "active"
        return Status(
            reachable=self._healthy(self.spec.url),
            container=self._container_state() if self._which("podman") else "podman-missing",
            autostart_enabled=enabled,
            autostart_active=active,
            linger=self._linger(),
            legacy_container="running" if self._which("podman") and self._legacy_running() else "",
        )

    def logs(self, tail: int = 50, follow: bool = False) -> int:
        cmd = [self._podman(), "logs", f"--tail={tail}"]
        if follow:
            cmd.append("-f")
        return self._run([*cmd, self.spec.name]).returncode
