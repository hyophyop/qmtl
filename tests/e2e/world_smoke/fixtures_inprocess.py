from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import uvicorn

from tests.e2e.world_smoke.servers.worldservice_stub import app as ws_app
from qmtl.services.gateway.api import create_app
from qmtl.services.gateway.ws import WebSocketHub


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
        except Exception as e:  # noqa: PERF203
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {url}: {last_err}")


class _Server:
    def __init__(self, app, host: str, port: int) -> None:
        self.config = uvicorn.Config(app, host=host, port=port, log_level="warning")
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


@pytest.fixture(scope="session", autouse=True)
def inproc_stack():
    """Start stub WorldService and Gateway in-process when requested.

    Enabled when USE_INPROC_WS_STACK=1 (or true/yes). Sets env vars that the
    e2e service-mode tests rely on and tears down servers at session end.
    """
    if os.environ.get("USE_INPROC_WS_STACK", "").lower() not in {"1", "true", "yes"}:
        # Ensure we behave like a generator fixture even when disabled
        yield None
        return

    ws_port = _find_free_port()
    gw_port = _find_free_port()

    ws = _Server(ws_app, "127.0.0.1", ws_port)
    ws.start()
    _wait_http(f"http://127.0.0.1:{ws_port}/health", timeout=15)

    # Build Gateway app pointing to the in-process WS
    gw_app = create_app(
        ws_hub=WebSocketHub(),
        worldservice_url=f"http://127.0.0.1:{ws_port}",
        enable_worldservice_proxy=True,
        enable_background=False,
        database_backend="sqlite",
        database_dsn=":memory:",
        enforce_live_guard=False,
    )
    gw = _Server(gw_app, "127.0.0.1", gw_port)
    gw.start()
    _wait_http(f"http://127.0.0.1:{gw_port}/health", timeout=15)

    os.environ.setdefault("WS_MODE", "service")
    os.environ["WORLDS_BASE_URL"] = f"http://127.0.0.1:{ws_port}"
    os.environ["GATEWAY_URL"] = f"http://127.0.0.1:{gw_port}"
    os.environ["QMTL_METRICS_URL"] = f"http://127.0.0.1:{gw_port}/metrics"
    os.environ.setdefault("QMTL_WS_STUB", "1")

    # Pre-register example worlds into the stub
    def _post_yaml(url: str, yml_path: Path) -> None:
        data = yml_path.read_bytes()
        req = urllib.request.Request(url.rstrip("/") + "/worlds", data=data, method="POST")
        req.add_header("Content-Type", "application/x-yaml")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status in (200, 201)

    try:
        base = Path("tests/e2e/world_smoke/worlds")
        _post_yaml(os.environ["WORLDS_BASE_URL"], base / "prod-us-equity.yml")
        _post_yaml(os.environ["WORLDS_BASE_URL"], base / "sandbox-crypto.yml")
    except Exception:
        pass

    try:
        yield {"gateway": os.environ["GATEWAY_URL"], "worlds": os.environ["WORLDS_BASE_URL"], "metrics": os.environ["QMTL_METRICS_URL"]}
    finally:
        gw.stop()
        ws.stop()
