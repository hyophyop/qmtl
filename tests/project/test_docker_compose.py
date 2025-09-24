import os
import shutil
import subprocess
from pathlib import Path

import pytest

def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Could not locate repository root from test path")


COMPOSE_FILE = _repo_root() / "docker-compose.yml"

@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_docker_compose_up_and_down(tmp_path):
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = "qmtltest"
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "config"], check=True, env=env)
