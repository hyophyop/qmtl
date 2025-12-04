from __future__ import annotations

import os
import socket
import threading
import time
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import uvicorn
import yaml

from qmtl.services.gateway.api import create_app
from qmtl.services.gateway.ws import WebSocketHub
from tests.e2e.world_smoke.servers.worldservice_stub import app as ws_app

# Third-party websockets emits a deprecation warning in uvicorn; ignore so -Werror runs stay green.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")

@dataclass
class CoreLoopStackHandle:
    mode: str
    gateway_url: str
    worlds_url: str
    metrics_url: str | None
    world_ids: list[str]
    close: Callable[[], None] | None = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if 200 <= r.status < 500:
                    return
        except Exception as exc:  # noqa: PERF203
            last_err = exc
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {url}: {last_err}")


def _probe_health(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


class _Server:
    def __init__(self, app, host: str, port: int) -> None:
        # WebSocket support is unnecessary for the stub stack; disable to avoid websockets
        # imports that emit deprecation warnings under -Werror.
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning", ws="none")
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        try:
            self.server.should_exit = True
        except Exception:
            pass
        try:
            self.thread.join(timeout=5)
        except Exception:
            pass


class InProcessCoreLoopStack:
    """Spin up stub WorldService + Gateway locally for contract tests."""

    def __init__(self, worlds_dir: Path) -> None:
        self._worlds_dir = worlds_dir
        self._servers: list[_Server] = []
        self._env_backup: dict[str, str | None] = {}
        self._handle: CoreLoopStackHandle | None = None

    def start(self) -> CoreLoopStackHandle:
        if self._handle is not None:
            return self._handle

        ws_port = _find_free_port()
        gw_port = _find_free_port()

        ws_server = _Server(ws_app, "127.0.0.1", ws_port)
        ws_server.start()
        _wait_http(f"http://127.0.0.1:{ws_port}/health", timeout=15)

        gw_app = create_app(
            ws_hub=WebSocketHub(),
            worldservice_url=f"http://127.0.0.1:{ws_port}",
            enable_worldservice_proxy=True,
            enable_background=False,
            database_backend="sqlite",
            database_dsn=":memory:",
            enforce_live_guard=False,
        )
        gw_server = _Server(gw_app, "127.0.0.1", gw_port)
        gw_server.start()
        _wait_http(f"http://127.0.0.1:{gw_port}/health", timeout=15)

        self._servers = [gw_server, ws_server]
        self._env_backup = {
            "WS_MODE": os.environ.get("WS_MODE"),
            "WORLDS_BASE_URL": os.environ.get("WORLDS_BASE_URL"),
            "GATEWAY_URL": os.environ.get("GATEWAY_URL"),
            "QMTL_METRICS_URL": os.environ.get("QMTL_METRICS_URL"),
        }

        worlds_url = f"http://127.0.0.1:{ws_port}"
        gateway_url = f"http://127.0.0.1:{gw_port}"
        os.environ["WS_MODE"] = "service"
        os.environ["WORLDS_BASE_URL"] = worlds_url
        os.environ["GATEWAY_URL"] = gateway_url
        os.environ["QMTL_METRICS_URL"] = f"{gateway_url}/metrics"

        world_ids = self._seed_worlds(worlds_url, self._worlds_dir.glob("*.yml"))

        self._handle = CoreLoopStackHandle(
            mode="inproc",
            gateway_url=gateway_url,
            worlds_url=worlds_url,
            metrics_url=os.environ.get("QMTL_METRICS_URL"),
            world_ids=world_ids,
            close=self.stop,
        )
        return self._handle

    def stop(self) -> None:
        while self._servers:
            server = self._servers.pop()
            try:
                server.stop()
            except Exception:
                pass

        for key, val in self._env_backup.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

        self._handle = None

    @staticmethod
    def _seed_worlds(base_url: str, worlds: Iterable[Path]) -> list[str]:
        world_ids: list[str] = []
        for path in worlds:
            data = path.read_bytes()
            req = urllib.request.Request(f"{base_url.rstrip('/')}/worlds", data=data, method="POST")
            req.add_header("Content-Type", "application/x-yaml")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status not in (200, 201):
                        raise RuntimeError(f"failed to seed world {path}: {resp.status}")
            except Exception as exc:
                raise RuntimeError(f"failed to seed world {path}: {exc}") from exc

            try:
                doc = yaml.safe_load(path.read_text())
                wid = doc.get("world", {}).get("id")
                if wid:
                    world_ids.append(str(wid))
            except Exception:
                pass

        return world_ids


def _service_stack_from_env() -> CoreLoopStackHandle | None:
    if os.environ.get("CORE_LOOP_STACK_MODE") == "inproc":
        return None

    gateway = os.environ.get("GATEWAY_URL")
    worlds = os.environ.get("WORLDS_BASE_URL")
    if os.environ.get("WS_MODE") != "service" or not gateway or not worlds:
        return None

    health_url = f"{gateway.rstrip('/')}/health"
    if not _probe_health(health_url):
        if os.environ.get("CORE_LOOP_STACK_MODE") == "service":
            warnings.warn(f"gateway health check failed at {health_url}; falling back to in-process stack")
        return None

    world_ids_env: list[str] = []
    env_worlds = os.environ.get("CORE_LOOP_WORLD_IDS") or os.environ.get("CORE_LOOP_WORLD_ID")
    if env_worlds:
        world_ids_env = [w.strip() for w in env_worlds.split(",") if w.strip()]

    return CoreLoopStackHandle(
        mode="service",
        gateway_url=gateway.rstrip("/"),
        worlds_url=worlds.rstrip("/"),
        metrics_url=os.environ.get("QMTL_METRICS_URL"),
        world_ids=world_ids_env,
        close=None,
    )


def bootstrap_core_loop_stack(worlds_dir: Path) -> CoreLoopStackHandle:
    """Prefer an existing service stack; otherwise start a local stub stack."""
    service_handle = _service_stack_from_env()
    if service_handle is not None:
        return service_handle

    return InProcessCoreLoopStack(worlds_dir).start()
