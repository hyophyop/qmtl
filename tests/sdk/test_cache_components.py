from __future__ import annotations

import pytest
import xarray as xr

from qmtl.sdk import hash_utils as default_hash_utils
from qmtl.sdk.cache_backfill import BackfillMerger
from qmtl.sdk.cache_context import ContextSwitchStrategy
from qmtl.sdk.cache_reader import CacheWindowReader
from qmtl.sdk.cache_ring_buffer import RingBuffer


class _StubMetrics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str | None, str | None]] = []

    def observe_cross_context_cache_hit(
        self,
        node_id: str,
        world_id: str,
        execution_domain: str,
        *,
        as_of: str | None,
        partition: str | None,
    ) -> None:
        self.calls.append((node_id, world_id, execution_domain, as_of, partition))


def test_ring_buffer_append_and_replace() -> None:
    buf = RingBuffer(period=3)
    buf.append(1, "a")
    buf.append(2, "b")
    assert buf.items() == [(1, "a"), (2, "b")]
    assert buf.latest() == (2, "b")

    buf.append(3, "c")
    buf.append(4, "d")  # wrap
    assert buf.items() == [(2, "b"), (3, "c"), (4, "d")]

    buf.replace([(10, "x"), (20, "y")])
    assert buf.items() == [(10, "x"), (20, "y")]
    assert buf.latest() == (20, "y")


def test_backfill_merger_prefers_existing_payloads() -> None:
    buf = RingBuffer(period=4)
    buf.replace([(60, {"v": "live1"}), (120, {"v": "live2"})])

    merger = BackfillMerger(period=4)
    result = merger.merge(
        buf,
        60,
        [
            (60, {"v": "bf1"}),
            (120, {"v": "bf-dup"}),
            (180, {"v": "bf3"}),
            (240, {"v": "bf4"}),
        ],
    )

    assert result.bucketed_items == [
        (60, {"v": "bf1"}),
        (120, {"v": "bf-dup"}),
        (180, {"v": "bf3"}),
        (240, {"v": "bf4"}),
    ]
    assert result.ranges == [(60, 240)]
    # Existing payload for 120 should win over the backfilled duplicate.
    assert result.merged_items == [
        (60, {"v": "live1"}),
        (120, {"v": "live2"}),
        (180, {"v": "bf3"}),
        (240, {"v": "bf4"}),
    ]


def test_context_switch_strategy_emits_metric_on_change() -> None:
    metrics = _StubMetrics()
    strategy = ContextSwitchStrategy(metrics)

    context, cleared = strategy.ensure(
        "key-a",
        node_id="node-1",
        world_id="w1",
        execution_domain="backtest",
        had_data=False,
    )
    assert not cleared
    assert context.compute_key == "key-a"
    assert not metrics.calls

    _, cleared = strategy.ensure(
        "key-b",
        node_id="node-1",
        world_id="w2",
        execution_domain="live",
        as_of=123,
        partition="p1",
        had_data=True,
    )
    assert cleared
    assert metrics.calls == [("node-1", "w2", "live", "123", "p1")]

    _, cleared = strategy.ensure(
        "key-b",
        node_id="node-1",
        world_id="w3",
        execution_domain="live",
        had_data=True,
    )
    assert not cleared
    # No additional metric for metadata-only updates.
    assert len(metrics.calls) == 1


def test_cache_window_reader_exports_numpy_and_hashes() -> None:
    buf1 = RingBuffer(period=3)
    buf1.replace([(1, {"v": 1}), (2, {"v": 2})])
    buf2 = RingBuffer(period=3)
    buf2.replace([(10, {"v": "a"})])

    reader = CacheWindowReader({("u1", 1): buf1, ("u2", 1): buf2}, period=3)

    data = reader.view_data()
    assert data == {
        "u1": {1: [(1, {"v": 1}), (2, {"v": 2})]},
        "u2": {1: [(10, {"v": "a"})]},
    }

    snapshot = reader.snapshot()
    snapshot["u1"][1].append((99, {}))
    # Underlying buffers should remain unchanged.
    assert reader.view_data()["u1"][1] == [(1, {"v": 1}), (2, {"v": 2})]

    h1 = reader.input_window_hash(hash_utils=default_hash_utils)
    buf1.append(3, {"v": 3})
    h2 = reader.input_window_hash(hash_utils=default_hash_utils)
    assert h1 != h2

    da = reader.as_xarray()
    assert isinstance(da, xr.DataArray)
    assert da.shape == (2, 1, 3, 2)
    with pytest.raises(ValueError):
        da.data[0, 0, 0, 0] = 10

