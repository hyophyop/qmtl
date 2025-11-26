"""Test configuration and shared fixtures."""

import asyncio
from typing import List

import pytest
import pytest_asyncio
import yaml

from qmtl.runtime.sdk import configuration as sdk_configuration
from qmtl.runtime.sdk import runtime
from qmtl.runtime.sdk.arrow_cache import reload_arrow_cache


def _close_loops(loops: List[asyncio.AbstractEventLoop]) -> None:
    for loop in loops:
        if loop.is_closed():
            continue
        try:
            loop.close()
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def _track_and_close_event_loops():
    created: List[asyncio.AbstractEventLoop] = []
    orig_new_loop = asyncio.new_event_loop

    def tracking_new_loop():
        loop = orig_new_loop()
        created.append(loop)
        return loop

    asyncio.new_event_loop = tracking_new_loop
    try:
        yield
    finally:
        asyncio.new_event_loop = orig_new_loop
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            created.append(loop)
        except Exception:
            pass
        _close_loops(created)
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass


@pytest_asyncio.fixture
async def fake_redis():
    fakeredis_aioredis = pytest.importorskip(
        "fakeredis.aioredis",
        reason="fakeredis is required for Redis-backed runtime tests",
    )
    redis = fakeredis_aioredis.FakeRedis(decode_responses=True)
    try:
        yield redis
    finally:
        if hasattr(redis, "aclose"):
            await redis.aclose(close_connection_pool=True)
        else:
            await redis.close()


@pytest.fixture
def configure_sdk(tmp_path, monkeypatch):
    def _apply(data: dict, *, filename: str = "qmtl.yml") -> str:
        cfg_path = tmp_path / filename
        cfg_path.write_text(yaml.safe_dump(data))
        monkeypatch.chdir(tmp_path)
        sdk_configuration.reset_runtime_config_cache()
        runtime.reload()
        reload_arrow_cache()
        return str(cfg_path)

    try:
        yield _apply
    finally:
        sdk_configuration.reset_runtime_config_cache()
        runtime.reload()
        reload_arrow_cache()
