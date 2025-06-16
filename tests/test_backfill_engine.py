import asyncio
import time
import logging
import pandas as pd
import pytest

from qmtl.sdk.node import SourceNode, StreamInput
from qmtl.sdk.backfill_engine import BackfillEngine


class DummySource:
    def __init__(self, df: pd.DataFrame, delay: float = 0.05, fail: int = 0) -> None:
        self.df = df
        self.delay = delay
        self.fail = fail
        self.calls = 0

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        self.calls += 1
        if self.calls <= self.fail:
            raise RuntimeError("fail")
        await asyncio.sleep(self.delay)
        return self.df


@pytest.mark.asyncio
async def test_concurrent_backfill_and_live_append():
    node = SourceNode(interval=60, period=5)
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
    node = SourceNode(interval=60, period=2)
    df = pd.DataFrame([{"ts": 60, "v": 1}])
    src = DummySource(df, delay=0.01, fail=1)
    engine = BackfillEngine(src, max_retries=2)
    engine.submit(node, 60, 60)
    await engine.wait()
    assert src.calls == 2
    assert node.cache.latest(node.node_id, 60) == (60, {"ts": 60, "v": 1})


@pytest.mark.asyncio
async def test_metrics_and_logs(caplog):
    from qmtl.sdk import metrics as sdk_metrics
    sdk_metrics.reset_metrics()

    node = SourceNode(interval=60, period=1)
    df = pd.DataFrame([{"ts": 60, "v": 1}])
    src = DummySource(df, delay=0.0, fail=1)
    engine = BackfillEngine(src, max_retries=2)

    with caplog.at_level(logging.INFO):
        engine.submit(node, 60, 60)
        await engine.wait()

    node_id = node.node_id
    assert sdk_metrics.backfill_jobs_in_progress._val == 0
    assert sdk_metrics.backfill_last_timestamp._vals[(node_id, "60")] == 60
    assert sdk_metrics.backfill_retry_total._vals[(node_id, "60")] == 1
    assert sdk_metrics.backfill_failure_total._vals.get((node_id, "60"), 0) == 0

    msgs = [r.message for r in caplog.records]
    assert "backfill.start" in msgs
    assert "backfill.retry" in msgs
    assert "backfill.complete" in msgs


@pytest.mark.asyncio
async def test_failure_metrics_and_logs(caplog):
    from qmtl.sdk import metrics as sdk_metrics
    sdk_metrics.reset_metrics()

    node = SourceNode(interval=60, period=1)
    df = pd.DataFrame([])
    src = DummySource(df, delay=0.0, fail=5)
    engine = BackfillEngine(src, max_retries=2)

    with caplog.at_level(logging.INFO):
        engine.submit(node, 0, 0)
        with pytest.raises(RuntimeError):
            await engine.wait()

    key = (node.node_id, "60")
    assert sdk_metrics.backfill_failure_total._vals[key] == 1
    assert sdk_metrics.backfill_retry_total._vals[key] == 3
    assert sdk_metrics.backfill_jobs_in_progress._val == 0
    msgs = [r.message for r in caplog.records]
    assert msgs.count("backfill.retry") >= 3
    assert "backfill.failed" in msgs


@pytest.mark.asyncio
async def test_streaminput_load_history():
    df = pd.DataFrame([
        {"ts": 60, "v": 1},
        {"ts": 120, "v": 2},
    ])
    src = DummySource(df, delay=0.0)
    stream = StreamInput(
        interval=60,
        period=3,
        history_provider=src,
    )
    await stream.load_history(60, 120)
    assert stream.cache.get_slice(stream.node_id, 60, count=2) == [
        (60, {"ts": 60, "v": 1}),
        (120, {"ts": 120, "v": 2}),
    ]
