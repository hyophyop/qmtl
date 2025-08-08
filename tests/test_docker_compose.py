import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

COMPOSE_FILE = Path(__file__).with_name("docker-compose.yml")

@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_docker_compose_up_and_down(tmp_path):
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = "qmtltest"
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"], check=True, env=env)
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down"], check=True, env=env)
