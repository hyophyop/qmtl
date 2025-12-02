import asyncio
from typing import Any, cast

import redis.asyncio as redis

import pytest

from qmtl.services.gateway import api
from qmtl.services.gateway.commit_log_consumer import CommitLogConsumer
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer
from qmtl.services.gateway.dagmanager_client import DagManagerClient
from qmtl.services.gateway.database import Database
from qmtl.services.gateway.world_client import WorldServiceClient
from qmtl.services.gateway.ws.hub import WebSocketHub


class _DummyComponent:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.ws_hub = None

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class _DummyCommitConsumer(_DummyComponent):
    def __init__(self) -> None:
        super().__init__()
        self.consume_calls: list[tuple[Any, int]] = []

    async def start(self) -> None:
        await super().start()

    async def consume(self, handler, timeout_ms: int) -> None:  # pragma: no cover - exercised via task
        self.consume_calls.append((handler, timeout_ms))
        await asyncio.sleep(0.01)


class _DummyHub(_DummyComponent):
    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.stopped = False


class _DummyCloseable:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _DummyRedis:
    def __init__(self) -> None:
        self.closed = False
        self.pool_closed = False
        self.connection_pool = self

    async def aclose(self) -> None:
        self.closed = True

    async def disconnect(self) -> None:
        self.pool_closed = True


class _DummyWorldClient:
    def __init__(self) -> None:
        self.closed = False
        self._client = self

    async def aclose(self) -> None:  # pragma: no cover - exercised via wrapper
        self.closed = True


@pytest.mark.asyncio
async def test_start_background_initializes_components() -> None:
    ws_hub, controlbus, commit_consumer, commit_task = await _start_components()
    try:
        assert commit_task is not None
        assert controlbus.started is True
        assert controlbus.ws_hub is ws_hub
        assert commit_consumer.started is True
        assert ws_hub.started is True
    finally:
        await _stop_components(commit_task, ws_hub, controlbus, commit_consumer)


@pytest.mark.asyncio
async def test_stop_background_cleans_up() -> None:
    ws_hub, controlbus, commit_consumer, commit_task = await _start_components()
    dagmanager = _DummyCloseable()
    database = _DummyCloseable()
    redis_conn = _DummyRedis()
    world_client = _DummyWorldClient()

    await api._stop_background(
        commit_task=commit_task,
        ws_hub=ws_hub,
        controlbus_consumer=controlbus,
        commit_log_consumer=commit_consumer,
        commit_log_writer=None,
        dagmanager=cast(DagManagerClient, dagmanager),
        database_obj=cast(Database, database),
        redis_conn=cast(redis.Redis, redis_conn),
        world_client=cast(WorldServiceClient, world_client),
    )

    assert controlbus.stopped is True
    assert commit_consumer.stopped is True
    assert commit_consumer.consume_calls
    assert commit_task.cancelled()
    assert ws_hub.stopped is True
    assert dagmanager.closed is True
    assert database.closed is True


async def _start_components():
    ws_hub = _DummyHub()
    controlbus = _DummyComponent()
    commit_consumer = _DummyCommitConsumer()
    commit_task = await api._start_background(
        enable_background=True,
        controlbus_consumer=cast(ControlBusConsumer, controlbus),
        commit_log_consumer=cast(CommitLogConsumer, commit_consumer),
        commit_log_handler=None,
        ws_hub=cast(WebSocketHub, ws_hub),
    )
    await asyncio.sleep(0.02)
    return ws_hub, controlbus, commit_consumer, commit_task


async def _stop_components(commit_task, ws_hub, controlbus, commit_consumer):
    dagmanager = _DummyCloseable()
    database = _DummyCloseable()
    redis_conn = _DummyRedis()
    world_client = _DummyWorldClient()
    await api._stop_background(
        commit_task=commit_task,
        ws_hub=ws_hub,
        controlbus_consumer=controlbus,
        commit_log_consumer=commit_consumer,
        commit_log_writer=None,
        dagmanager=cast(DagManagerClient, dagmanager),
        database_obj=cast(Database, database),
        redis_conn=cast(redis.Redis, redis_conn),
        world_client=cast(WorldServiceClient, world_client),
    )
    assert redis_conn.closed is True
    assert redis_conn.pool_closed is True
    assert world_client.closed is True


@pytest.mark.asyncio
async def test_background_disabled_skips_start() -> None:
    ws_hub = _DummyHub()
    controlbus = _DummyComponent()
    commit_consumer = _DummyCommitConsumer()

    commit_task = await api._start_background(
        enable_background=False,
        controlbus_consumer=cast(ControlBusConsumer, controlbus),
        commit_log_consumer=cast(CommitLogConsumer, commit_consumer),
        commit_log_handler=None,
        ws_hub=cast(WebSocketHub, ws_hub),
    )

    assert commit_task is None
    assert controlbus.started is False
    assert commit_consumer.started is False
    assert ws_hub.started is False
