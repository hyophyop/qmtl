import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from qmtl.sdk.runner import Runner

@pytest_asyncio.fixture
async def fake_redis():
    redis = FakeRedis(decode_responses=True)
    try:
        yield redis
    finally:
        if hasattr(redis, "aclose"):
            await redis.aclose(close_connection_pool=True)
        else:
            await redis.close()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_runner_client():
    yield
    await Runner.aclose_http_client()
