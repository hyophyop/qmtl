import logging
import pytest

from qmtl.services.gateway.redis_queue import RedisTaskQueue


class _FailPushRedis:
    async def rpush(self, name: str, value: str) -> None:  # pragma: no cover - behaviour is tested
        raise RuntimeError("fail-push")


class _FailPopRedis:
    async def lpop(self, name: str) -> None:  # pragma: no cover - behaviour is tested
        raise RuntimeError("fail-pop")


@pytest.mark.asyncio
async def test_push_failure_logs_and_returns_false(caplog):
    queue = RedisTaskQueue(_FailPushRedis(), "q")
    caplog.set_level(logging.ERROR)
    assert await queue.push("x") is False
    assert any("q" in r.message and "fail-push" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_pop_failure_logs_and_returns_none(caplog):
    queue = RedisTaskQueue(_FailPopRedis(), "q")
    caplog.set_level(logging.ERROR)
    assert await queue.pop() is None
    assert any("q" in r.message and "fail-pop" in r.message for r in caplog.records)
