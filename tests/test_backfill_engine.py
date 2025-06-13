import asyncio
import time
import pandas as pd
import pytest

from qmtl.sdk.node import Node
from qmtl.sdk.backfill_engine import BackfillEngine


class DummySource:
    def __init__(self, df: pd.DataFrame, delay: float = 0.05, fail: int = 0) -> None:
        self.df = df
        self.delay = delay
        self.fail = fail
        self.calls = 0

    def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        self.calls += 1
        if self.calls <= self.fail:
            raise RuntimeError("fail")
        time.sleep(self.delay)
        return self.df


@pytest.mark.asyncio
async def test_concurrent_backfill_and_live_append():
    node = Node(interval=60, period=5)
    df = pd.DataFrame([
        {"ts": 60, "value": 1},
        {"ts": 120, "value": 2},
        {"ts": 180, "value": 3},
    ])
    src = DummySource(df, delay=0.05)
    engine = BackfillEngine(src)

    engine.submit(node, 60, 180)
    await asyncio.sleep(0)  # ensure task started
    await asyncio.to_thread(node.feed, node.node_id, 60, 180, {"v": "live"})
    await asyncio.to_thread(node.feed, node.node_id, 60, 240, {"v": "live2"})

    await engine.wait()

    assert node.cache.get_slice(node.node_id, 60, count=5) == [
        (60, {"ts": 60, "value": 1}),
        (120, {"ts": 120, "value": 2}),
        (180, {"v": "live"}),
        (240, {"v": "live2"}),
    ]
    assert node.cache.backfill_state.is_complete(node.node_id, 60, 60, 180)


@pytest.mark.asyncio
async def test_retry_logic():
    node = Node(interval=60, period=2)
    df = pd.DataFrame([{"ts": 60, "v": 1}])
    src = DummySource(df, delay=0.01, fail=1)
    engine = BackfillEngine(src, max_retries=2)
    engine.submit(node, 60, 60)
    await engine.wait()
    assert src.calls == 2
    assert node.cache.latest(node.node_id, 60) == (60, {"ts": 60, "v": 1})
