import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

@pytest_asyncio.fixture
async def fake_redis():
    redis = FakeRedis(decode_responses=True)
    try:
        yield redis
    finally:
        await redis.close()
