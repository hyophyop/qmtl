from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest


def _wait_http(url: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if 200 <= r.status < 500:
                    return
        except Exception as e:  # noqa: PERF203 - simple polling
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {url}: {last_err}")


def _compose_port(compose: str, service: str, container_port: int) -> str:
    import subprocess
    out = subprocess.check_output(["docker", "compose", "-f", compose, "port", service, str(container_port)], text=True)
    # Expected like: "127.0.0.1:49153" (first line). Grab host:port, return full http URL.
    line = out.strip().splitlines()[0].strip()
    # In case output is "127.0.0.1:49153" → extract port
    return line


@pytest.fixture(scope="session")
def ws_stack() -> dict[str, str]:
    """Bring up stub WorldService + Gateway via Docker Compose for this session.

    Activated only when USE_DOCKER_WS_STACK=1. Otherwise, skips and returns {}.
    """
    if os.environ.get("USE_DOCKER_WS_STACK") not in {"1", "true", "yes"}:
        pytest.skip("docker WS stack disabled; set USE_DOCKER_WS_STACK=1")

    compose = os.path.join(os.path.dirname(__file__), "docker-compose.yml")
    up_cmd = ["docker", "compose", "-f", compose, "up", "-d", "--build"]
    down_cmd = ["docker", "compose", "-f", compose, "down", "-v"]

    try:
        subprocess.check_call(up_cmd)
    except Exception as e:
        pytest.skip(f"failed to start docker stack: {e}")

    # Query dynamically assigned host ports
    try:
        ws_host = _compose_port(compose, "worldservice", 18080)
        gw_host = _compose_port(compose, "gateway", 8000)
    except Exception as e:
        # If port inspection fails, tear down and skip
        try:
            subprocess.check_call(down_cmd)
        except Exception:
            pass
        pytest.skip(f"failed to determine mapped ports: {e}")

    # Build http base URLs from host:port
    ws = f"http://{ws_host}"
    gw = f"http://{gw_host}"
    try:
        _wait_http(f"{ws}/health", timeout=25)
        _wait_http(f"{gw}/health", timeout=25)
    except Exception as e:
        # Tear down if unhealthy
        try:
            subprocess.check_call(down_cmd)
        except Exception:
            pass
        pytest.skip(f"stack did not become healthy: {e}")

    # Export common envs for tests that rely on svc_env fixture
    os.environ.setdefault("WS_MODE", "service")
    os.environ.setdefault("GATEWAY_URL", gw)
    os.environ.setdefault("WORLDS_BASE_URL", ws)
    os.environ.setdefault("QMTL_METRICS_URL", f"{gw}/metrics")
    os.environ.setdefault("QMTL_WS_STUB", "1")

    # Pre-register example worlds so tests don't skip on 404
    def _post_yaml(url: str, yml_path: Path) -> None:
        data = yml_path.read_bytes()
        req = urllib.request.Request(url.rstrip("/") + "/worlds", data=data, method="POST")
        req.add_header("Content-Type", "application/x-yaml")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status in (200, 201)

    try:
        base = Path("tests/e2e/world_smoke/worlds")
        _post_yaml(ws, base / "prod-us-equity.yml")
        _post_yaml(ws, base / "sandbox-crypto.yml")
    except Exception:
        # Registration failures should not break suite; tests can still skip
        pass

    yield {"gateway": gw, "worlds": ws, "metrics": f"{gw}/metrics"}

    try:
        subprocess.check_call(down_cmd)
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def maybe_start_ws_stack(request):
    """Auto-start docker WS stack when USE_DOCKER_WS_STACK=1.

    Ensures env vars are set before other fixtures (like svc_env) run.
    """
    if os.environ.get("USE_DOCKER_WS_STACK") in {"1", "true", "yes"}:
        return request.getfixturevalue("ws_stack")
    return None
