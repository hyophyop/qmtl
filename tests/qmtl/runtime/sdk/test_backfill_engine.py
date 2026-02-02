import asyncio
import logging
from typing import Any

import polars as pl
import pytest

from qmtl.foundation.common.metrics_factory import get_mapping_store
from qmtl.runtime.sdk.node import SourceNode, StreamInput
from qmtl.runtime.sdk.backfill_engine import BackfillEngine


class DummySource:
    def __init__(
        self,
        df: pl.DataFrame,
        delay: float = 0.05,
        fail: int = 0,
        metadata: Any | None = None,
    ) -> None:
        self.df = df
        self.delay = delay
        self.fail = fail
        self.calls = 0
        self.ready_calls = 0
        # Event used by tests to detect when ``fetch`` has been invoked.
        self.started = asyncio.Event()
        self.metadata = metadata
        self.last_fetch_metadata = None

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pl.DataFrame:
        self.calls += 1
        self.started.set()
        if self.calls <= self.fail:
            raise RuntimeError("fail")
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        loop.call_later(self.delay, fut.set_result, None)
        await fut
        self.last_fetch_metadata = self.metadata
        return self.df

    async def ready(self) -> bool:
        self.ready_calls += 1
        await asyncio.sleep(0)
        return True


@pytest.mark.asyncio
async def test_concurrent_backfill_and_live_append():
    node = SourceNode(interval="60s", period=5)
    df = pl.DataFrame([
        {"ts": 60, "value": 1},
        {"ts": 120, "value": 2},
        {"ts": 180, "value": 3},
    ])
    src = DummySource(df, delay=0.05)
    engine = BackfillEngine(src)

    engine.submit(node, 60, 180)
    await src.started.wait()
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
    node = SourceNode(interval="60s", period=2)
    df = pl.DataFrame([{"ts": 60, "v": 1}])
    src = DummySource(df, delay=0.01, fail=1)
    engine = BackfillEngine(src, max_retries=2)
    engine.submit(node, 60, 60)
    await engine.wait()
    assert src.calls == 2
    assert src.ready_calls >= 1
    assert node.cache.latest(node.node_id, 60) == (60, {"ts": 60, "v": 1})


@pytest.mark.asyncio
async def test_metrics_and_logs(caplog):
    from qmtl.runtime.sdk import metrics as sdk_metrics
    sdk_metrics.reset_metrics()

    node = SourceNode(interval="60s", period=1)
    df = pl.DataFrame([{"ts": 60, "v": 1}])
    src = DummySource(df, delay=0.0, fail=1)
    engine = BackfillEngine(src, max_retries=2)

    with caplog.at_level(logging.INFO):
        engine.submit(node, 60, 60)
        await engine.wait()

    node_id = node.node_id
    assert sdk_metrics.backfill_jobs_in_progress._val == 0
    timestamp_store = get_mapping_store(sdk_metrics.backfill_last_timestamp, dict)
    retry_store = get_mapping_store(sdk_metrics.backfill_retry_total, dict)
    failure_store = get_mapping_store(sdk_metrics.backfill_failure_total, dict)
    assert timestamp_store[(node_id, "60")] == 60
    assert retry_store[(node_id, "60")] == 1
    assert failure_store.get((node_id, "60"), 0) == 0

    msgs = [r.message for r in caplog.records]
    assert "backfill.start" in msgs
    assert "backfill.retry" in msgs
    assert "backfill.complete" in msgs


@pytest.mark.asyncio
async def test_failure_metrics_and_logs(caplog):
    from qmtl.runtime.sdk import metrics as sdk_metrics
    sdk_metrics.reset_metrics()

    node = SourceNode(interval="60s", period=1)
    df = pl.DataFrame([])
    src = DummySource(df, delay=0.0, fail=5)
    engine = BackfillEngine(src, max_retries=2)

    with caplog.at_level(logging.INFO):
        engine.submit(node, 0, 0)
        with pytest.raises(RuntimeError):
            await engine.wait()

    key = (node.node_id, "60")
    failure_store = get_mapping_store(sdk_metrics.backfill_failure_total, dict)
    retry_store = get_mapping_store(sdk_metrics.backfill_retry_total, dict)
    assert failure_store[key] == 1
    assert retry_store[key] == 3
    assert sdk_metrics.backfill_jobs_in_progress._val == 0
    msgs = [r.message for r in caplog.records]
    assert msgs.count("backfill.retry") >= 3
    assert "backfill.failed" in msgs


@pytest.mark.asyncio
async def test_streaminput_load_history():
    df = pl.DataFrame([
        {"ts": 60, "v": 1},
        {"ts": 120, "v": 2},
    ])
    src = DummySource(df, delay=0.0)
    stream = StreamInput(
        interval="60s",
        period=3,
        history_provider=src,
    )
    await stream.load_history(60, 120)
    assert stream.cache.get_slice(stream.node_id, 60, count=2) == [
        (60, {"ts": 60, "v": 1}),
        (120, {"ts": 120, "v": 2}),
    ]


@pytest.mark.asyncio
async def test_metadata_publish(monkeypatch):
    from qmtl.runtime.io.artifact import ArtifactPublication
    from qmtl.runtime.sdk.seamless_data_provider import SeamlessFetchMetadata
    from qmtl.runtime.sdk.runner import Runner

    node = StreamInput(interval="60s", period=2)
    node.strategy_id = "strategy-1"
    node.gateway_url = "http://gateway"
    node.world_id = "world-123"
    node.execution_domain = "live"

    artifact = ArtifactPublication(
        dataset_fingerprint="fp123",
        as_of="2024-10-10T00:00:00Z",
        node_id=node.node_id,
        start=60,
        end=120,
        rows=2,
        uri="local://artifact",
    )
    metadata = SeamlessFetchMetadata(
        node_id=node.node_id,
        interval=60,
        requested_range=(60, 120),
        rows=2,
        coverage_bounds=(60, 120),
        conformance_flags={"gap": 1},
        conformance_warnings=("gap",),
        dataset_fingerprint="fp123",
        as_of="2024-10-10T00:00:00Z",
        manifest_uri="local://manifest",
        artifact=artifact,
    )

    df = pl.DataFrame([
        {"ts": 60, "v": 1},
        {"ts": 120, "v": 2},
    ])
    src = DummySource(df, delay=0.0, metadata=metadata)
    engine = BackfillEngine(src)

    calls: list[dict[str, Any]] = []

    async def fake_post_history_metadata(self, *, gateway_url, strategy_id, payload):
        calls.append({
            "gateway_url": gateway_url,
            "strategy_id": strategy_id,
            "payload": payload,
        })

    monkeypatch.setattr(
        Runner.services().gateway_client,
        "post_history_metadata",
        fake_post_history_metadata.__get__(
            Runner.services().gateway_client,
            Runner.services().gateway_client.__class__
        ),
    )

    engine.submit(node, 60, 120)
    await engine.wait()

    assert node.dataset_fingerprint == "fp123"
    assert node.compute_context.dataset_fingerprint == "fp123"
    assert node.last_fetch_metadata is metadata
    assert len(calls) == 1
    call = calls[0]
    assert call["gateway_url"] == "http://gateway"
    assert call["strategy_id"] == "strategy-1"
    payload = call["payload"]
    assert payload["dataset_fingerprint"] == "fp123"
    assert payload["as_of"] == "2024-10-10T00:00:00Z"
    assert payload["coverage_bounds"] == [60, 120]
    assert payload["artifact"]["rows"] == 2


@pytest.mark.asyncio
async def test_metadata_publish_handles_failure(monkeypatch, caplog):
    from qmtl.runtime.sdk.seamless_data_provider import SeamlessFetchMetadata
    from qmtl.runtime.sdk.runner import Runner

    node = StreamInput(interval="60s", period=2)
    node.strategy_id = "strategy-1"
    node.gateway_url = "http://gateway"
    node.world_id = "world-123"

    metadata = SeamlessFetchMetadata(
        node_id=node.node_id,
        interval=60,
        requested_range=(60, 120),
        rows=0,
        coverage_bounds=None,
        conformance_flags={},
        conformance_warnings=(),
        dataset_fingerprint=None,
        as_of=None,
        manifest_uri=None,
        artifact=None,
    )

    df = pl.DataFrame(schema={"ts": pl.Int64, "v": pl.Float64})
    src = DummySource(df, delay=0.0, metadata=metadata)
    engine = BackfillEngine(src)

    async def failing_post(*_, **__):
        raise RuntimeError("boom")

    caplog.set_level(logging.DEBUG, logger="qmtl.runtime.sdk.backfill_engine")
    monkeypatch.setattr(
        Runner.services().gateway_client,
        "post_history_metadata",
        failing_post,
    )

    engine.submit(node, 60, 120)
    await engine.wait()

    assert any(
        "failed to publish seamless metadata" in r.getMessage()
        for r in caplog.records
        if r.name == "qmtl.runtime.sdk.backfill_engine"
    )
