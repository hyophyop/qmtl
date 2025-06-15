import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import asyncpg
import httpx
import pytest
import redis.asyncio as redis

from qmtl.sdk.runner import Runner
from ..sample_strategy import SampleStrategy

COMPOSE_FILE = Path(__file__).with_name("docker-compose.e2e.yml")


@pytest.fixture(scope="module")
def compose_stack():
    if shutil.which("docker") is None:
        pytest.skip("docker not installed")
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = "qmtle2e"
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"], check=True, env=env)
    try:
        Runner.wait_gateway("http://localhost:8000")
        yield
    finally:
        subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down"], check=True, env=env)


@pytest.mark.asyncio
async def test_full_flow(compose_stack):
    strategy = Runner.dryrun(SampleStrategy, gateway_url="http://localhost:8000")
    strategy_id = getattr(strategy, "strategy_id", None)
    assert strategy_id
    queue_map = {n.node_id: n.queue_topic for n in strategy.nodes if n.queue_topic}
    assert queue_map

    async with httpx.AsyncClient() as client:
        status = "queued"
        for _ in range(30):
            resp = await client.get(f"http://localhost:8000/strategies/{strategy_id}/status")
            if resp.status_code == 200:
                status = resp.json().get("status", status)
                if status != "queued":
                    break
            await asyncio.sleep(1)
        assert status in {"processing", "running", "completed"}

    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    assert await r.hexists(f"strategy:{strategy_id}", "dag")

    conn = await asyncpg.connect("postgresql://postgres:example@localhost/postgres")
    db_status = await conn.fetchval("SELECT status FROM strategies WHERE id=$1", strategy_id)
    await conn.close()
    assert db_status is not None
