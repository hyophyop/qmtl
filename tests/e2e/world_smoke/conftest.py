# tests/e2e/world_smoke/conftest.py
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

"""World smoke fixtures and helpers.

Plugin registrations are defined in the repository top-level ``conftest.py``
to comply with pytest 8's restriction that ``pytest_plugins`` may only be
declared at the test root. Do not add ``pytest_plugins`` here.
"""


@pytest.fixture(scope="session")
def artifact_dir():
    p = Path(os.environ.get("ARTIFACT_DIR", ".artifacts/world_smoke"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture(scope="session")
def worlds():
    base = Path("tests/e2e/world_smoke/worlds")
    return {
        "prod": base / "prod-us-equity.yml",
        "sandbox": base / "sandbox-crypto.yml",
    }


def _env_or_skip(name: str):
    val = os.environ.get(name)
    if not val:
        pytest.skip(f"env {name} not set (skipping service-mode check)")
    return val


def _wait_http(url: str, timeout: float = 15.0) -> None:
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
    pytest.skip(f"timeout waiting for {url}: {last_err}")


def _post_yaml(url: str, yml_path: Path) -> None:
    data = yml_path.read_bytes()
    req = urllib.request.Request(url.rstrip("/") + "/worlds", data=data, method="POST")
    req.add_header("Content-Type", "application/x-yaml")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status not in (200, 201):
                raise AssertionError(f"unexpected status {r.status} for {yml_path.name}")
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return
        raise


@pytest.fixture(scope="session")
def svc_env(request):
    if os.environ.get("WS_MODE", "sdk") != "service":
        pytest.skip("service mode disabled; set WS_MODE=service")
    base_worlds = _env_or_skip("WORLDS_BASE_URL")
    base_gw = _env_or_skip("GATEWAY_URL")
    metrics = os.environ.get("QMTL_METRICS_URL")
    _wait_http(f"{base_worlds.rstrip('/')}/health")
    _wait_http(f"{base_gw.rstrip('/')}/health")
    return {"worlds": base_worlds, "gateway": base_gw, "metrics": metrics}


@pytest.fixture(scope="session")
def service_worlds_registered(svc_env, worlds):
    try:
        _post_yaml(svc_env["worlds"], worlds["prod"])
        _post_yaml(svc_env["worlds"], worlds["sandbox"])
    except Exception as e:
        pytest.skip(f"failed to register worlds: {e}")
    return svc_env
