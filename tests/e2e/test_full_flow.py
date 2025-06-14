import os
import shutil
import subprocess
import time
from pathlib import Path

import asyncio

import asyncpg
import httpx
import pytest
import redis.asyncio as redis

from qmtl.sdk import Runner
from qmtl.gateway import StrategyFSM, DagManagerClient, StrategyWorker, RedisFIFOQueue
from qmtl.gateway.api import PostgresDatabase
from ..sample_strategy import SampleStrategy

COMPOSE_FILE = Path(__file__).with_name("docker-compose.e2e.yml")


@pytest.fixture(scope="module")
def docker_stack():
    if shutil.which("docker") is None:
        pytest.skip("docker not installed")
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = "qmtle2e"
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"], check=True, env=env)
    try:
        yield
    finally:
        subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down"], check=True, env=env)


def _wait_for_service(service: str, timeout: int = 60) -> None:
    env = {"COMPOSE_PROJECT_NAME": "qmtle2e"}
    container = f"{env['COMPOSE_PROJECT_NAME']}-{service}-1"
    start = time.time()
    while time.time() - start < timeout:
        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container],
            capture_output=True,
            text=True,
            env=env,
        )
        status = inspect.stdout.strip()
        if status == "healthy":
            return
        if status == "unhealthy":
            logs = subprocess.run(
                ["docker", "compose", "-f", str(COMPOSE_FILE), "logs", service],
                capture_output=True,
                text=True,
                env=env,
            )
            raise RuntimeError(f"{service} unhealthy:\n{logs.stdout}")
        time.sleep(1)
    raise RuntimeError(f"{service} not healthy")


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
@pytest.mark.asyncio
async def test_full_flow(docker_stack):
    _wait_for_service("dag-manager")
    _wait_for_service("gateway")

    # Submit strategy via Runner
    strategy = Runner.dryrun(SampleStrategy, gateway_url="http://localhost:8000")
    assert any(n.queue_topic for n in strategy.nodes)

    # Connect to services
    pg_dsn = "postgresql://postgres:example@localhost:5432/postgres"
    conn = await asyncpg.connect(pg_dsn)
    try:
        row = await conn.fetchrow("SELECT strategy_id FROM event_log ORDER BY id DESC LIMIT 1")
        assert row is not None
        strategy_id = row["strategy_id"]
    finally:
        await conn.close()

    redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
    db = PostgresDatabase(pg_dsn)
    await db.connect()
    fsm = StrategyFSM(redis_client, db)
    queue = RedisFIFOQueue(redis_client, "strategy_queue")
    dag_client = DagManagerClient("localhost:50051")
    worker = StrategyWorker(redis_client, db, fsm, queue, dag_client)
    await worker.run_once()

    # Verify status transition
    async with httpx.AsyncClient() as client:
        for _ in range(30):
            resp = await client.get(f"http://localhost:8000/strategies/{strategy_id}/status")
            if resp.status_code == 200 and resp.json().get("status") != "queued":
                break
            await asyncio.sleep(1)
        assert resp.json().get("status") in {"processing", "completed", "failed"}

