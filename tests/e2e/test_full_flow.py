import base64
import json
import os
import socket
import subprocess
import time
import shutil
from pathlib import Path

import httpx
import pytest

from qmtl.sdk.runner import Runner
from tests.sample_strategy import SampleStrategy

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.e2e.yml"


def _wait_port(host: str, port: int, timeout: float = 60.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Timeout waiting for {host}:{port}")


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not installed"
)
def test_full_flow(monkeypatch):
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = f"qmtle2e{int(time.time())}"
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"], check=True, env=env)
    try:
        _wait_port("localhost", 50051)
        _wait_port("localhost", 8000)

        captured = {}

        def _post_gateway(*, gateway_url: str, dag: dict, meta, run_type: str) -> dict:
            url = gateway_url.rstrip("/") + "/strategies"
            payload = {
                "dag_json": base64.b64encode(json.dumps(dag).encode()).decode(),
                "meta": meta,
                "run_type": run_type,
            }
            resp = httpx.post(url, json=payload)
            captured["resp"] = resp
            if resp.status_code == 202:
                return resp.json().get("queue_map", {})
            resp.raise_for_status()
            return {}

        monkeypatch.setattr(Runner, "_post_gateway", staticmethod(_post_gateway))

        Runner.dryrun(SampleStrategy, gateway_url="http://localhost:8000")
        resp = captured.get("resp")
        assert resp is not None and resp.status_code == 202

        metrics = httpx.get("http://localhost:8000/metrics")
        assert metrics.status_code == 200
        lines = [line for line in metrics.text.splitlines() if line.startswith("gateway_e2e_latency_p95")]
        assert lines
        val = float(lines[0].split(" ")[1])
        assert val > 0
    finally:
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "down"],
            env=env,
            check=False,
        )
