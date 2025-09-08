# tests/e2e/world_smoke/conftest.py
import os
import pytest
from pathlib import Path

# Enable optional fixture modules for in-process and dockerized stacks
pytest_plugins = (
    "tests.e2e.world_smoke.fixtures_inprocess",
    "tests.e2e.world_smoke.fixtures_docker",
)


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


@pytest.fixture
def svc_env(request):
    if os.environ.get("WS_MODE", "sdk") != "service":
        pytest.skip("service mode disabled; set WS_MODE=service")
    base_worlds = _env_or_skip("WORLDS_BASE_URL")
    base_gw = _env_or_skip("GATEWAY_URL")
    metrics = os.environ.get("QMTL_METRICS_URL")
    return {"worlds": base_worlds, "gateway": base_gw, "metrics": metrics}
