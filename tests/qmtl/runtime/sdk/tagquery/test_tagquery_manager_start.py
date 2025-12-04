import asyncio

import pytest

from qmtl.runtime.sdk.tagquery_manager import TagQueryManager


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class DummyClient:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_start_is_idempotent_with_active_poll_loop():
    client = DummyClient()
    manager = TagQueryManager("http://gw", ws_client=client, world_id="w")

    await manager.start()
    first_task = manager._poll_task
    assert first_task is not None
    assert client.start_calls == 1

    await manager.start()
    assert client.start_calls == 1
    assert manager._poll_task is first_task

    await asyncio.sleep(0)
    await manager.stop()
    assert client.stop_calls == 1
    assert manager._poll_task is None

    await manager.start()
    assert client.start_calls == 2
    await manager.stop()
    assert client.stop_calls == 2
