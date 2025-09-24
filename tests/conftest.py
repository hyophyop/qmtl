import pytest
import pytest_asyncio

fakeredis_aioredis = pytest.importorskip(
    "fakeredis.aioredis",
    reason="fakeredis is required for Redis-backed runtime tests",
)
FakeRedis = fakeredis_aioredis.FakeRedis

from qmtl.runtime.sdk.runner import Runner

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


@pytest.fixture(autouse=True)
def _default_runner_context():
    context = {
        "execution_mode": "backtest",
        "clock": "virtual",
        "as_of": "2025-01-01T00:00:00Z",
        "dataset_fingerprint": "lake:blake3:test",
    }
    Runner.set_default_context(context)
    try:
        yield context
    finally:
        Runner.set_default_context(None)
