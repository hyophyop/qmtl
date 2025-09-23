import asyncio

import pytest

from qmtl.runtime.sdk import FakeLiveDataFeed


@pytest.mark.asyncio
async def test_fake_live_data_feed_emits_messages():
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)

    feed = FakeLiveDataFeed(on_message=on_message)
    await feed.start()
    await feed.emit({"foo": "bar"})
    await asyncio.sleep(0)
    await feed.stop()

    assert received == [{"foo": "bar"}]

    # Emitting after stop should not deliver
    await feed.emit({"foo": "baz"})
    await asyncio.sleep(0)
    assert received == [{"foo": "bar"}]
