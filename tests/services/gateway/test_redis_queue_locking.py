import asyncio
import pytest

from qmtl.services.gateway.redis_client import InMemoryRedis
from qmtl.services.gateway.redis_queue import RedisTaskQueue


@pytest.mark.asyncio
async def test_pop_respects_existing_lock():
    redis = InMemoryRedis()
    queue = RedisTaskQueue(redis, "q")

    await queue.push("strategy-1")
    assert await redis.set("lock:strategy-1", "worker-a", nx=True, px=60000)

    assert await queue.pop("worker-b") is None
    assert await redis.lindex("q", 0) == "strategy-1"


@pytest.mark.asyncio
async def test_release_allows_retry():
    redis = InMemoryRedis()
    queue = RedisTaskQueue(redis, "q")

    await queue.push("strategy-1")
    owner = "worker-a"
    item = await queue.pop(owner)
    assert item == "strategy-1"

    await queue.push(item)
    assert await queue.pop("worker-b") is None

    await queue.release(item, owner)
    retry_item = await queue.pop("worker-b")
    assert retry_item == item
    await queue.release(retry_item, "worker-b")


@pytest.mark.asyncio
async def test_lock_ttl_expires():
    redis = InMemoryRedis()
    queue = RedisTaskQueue(redis, "q", lock_ttl_ms=20)

    await queue.push("strategy-1")
    item = await queue.pop("worker-a")
    assert item == "strategy-1"

    await queue.push(item)
    await asyncio.sleep(0.05)

    retry_item = await queue.pop("worker-b")
    assert retry_item == item
    await queue.release(retry_item, "worker-b")
