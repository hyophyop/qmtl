"""Regression tests for four-dimensional tensor cache window management."""
from __future__ import annotations

import pytest

from qmtl.runtime.sdk import arrow_cache
from qmtl.runtime.sdk.cache import NodeCache


@pytest.fixture
def node_cache() -> NodeCache:
    return NodeCache(period=3)


def test_multi_interval_tensor_snapshot_and_ready_state(node_cache: NodeCache) -> None:
    """Cache stores independent windows per upstream/interval and only readies when all fill."""

    first_series = [60, 120, 180]
    for idx, ts in enumerate(first_series):
        node_cache.append("btc", 60, ts, {"idx": idx, "interval": 60})

    assert node_cache.ready() is True

    second_series = [300, 600, 900]
    for idx, ts in enumerate(second_series):
        node_cache.append("btc", 300, ts, {"idx": idx, "interval": 300})
        if idx < node_cache.period - 1:
            assert node_cache.ready() is False
    assert node_cache.ready() is True

    third_series = [60, 120, 180]
    for idx, ts in enumerate(third_series):
        node_cache.append("eth", 60, ts, {"idx": idx, "interval": 60})
        if idx < node_cache.period - 1:
            assert node_cache.ready() is False

    assert node_cache.ready() is True

    snapshot = node_cache._snapshot()
    assert snapshot["btc"][60][-1] == (180, {"idx": 2, "interval": 60})
    assert snapshot["btc"][300][-1] == (900, {"idx": 2, "interval": 300})
    assert snapshot["eth"][60][-1] == (180, {"idx": 2, "interval": 60})

    tensor = node_cache.as_xarray()
    assert tensor.dims == ("u", "i", "p", "f")
    assert tensor.sel(u="btc", i=60, p=2, f="t").item() == 180
    assert tensor.sel(u="btc", i=60, p=2, f="v").item() == {"idx": 2, "interval": 60}
    assert tensor.sel(u="btc", i=300, p=2, f="t").item() == 900
    assert tensor.sel(u="eth", i=60, p=1, f="t").item() == 120


def test_fifo_eviction_isolated_per_interval(node_cache: NodeCache) -> None:
    """Rolling windows evict oldest elements without affecting other intervals."""

    for step in range(5):
        node_cache.append("btc", 60, (step + 1) * 60, {"v": step})
    assert node_cache.get_slice("btc", 60, count=10) == [
        (180, {"v": 2}),
        (240, {"v": 3}),
        (300, {"v": 4}),
    ]

    # Populate another upstream/interval and ensure it retains its independent history.
    for step in range(3):
        node_cache.append("eth", 300, (step + 1) * 300, {"v": f"e{step}"})
    assert node_cache.get_slice("eth", 300, count=5) == [
        (300, {"v": "e0"}),
        (600, {"v": "e1"}),
        (900, {"v": "e2"}),
    ]

    # Memory usage is capped at period × feature width × sizeof(pointer) per buffer.
    expected_buffers = 2
    assert node_cache.resident_bytes == expected_buffers * node_cache.period * 2 * 8


def test_timestamp_bucket_gap_detection_and_out_of_order(node_cache: NodeCache) -> None:
    """Timestamps bucket to interval boundaries and gap detection resets on out-of-order data."""

    base = 1_700_000_000 - (1_700_000_000 % 60)
    node_cache.append("btc", 60, base + 37, {"v": 1})
    assert node_cache.get_slice("btc", 60, count=1)[0][0] == base
    assert node_cache.missing_flags()["btc"][60] is False
    assert node_cache.last_timestamps()["btc"][60] == base

    node_cache.append("btc", 60, base + 97, {"v": 2})
    assert node_cache.get_slice("btc", 60, count=2)[-1][0] == base + 60
    assert node_cache.missing_flags()["btc"][60] is False
    assert node_cache.last_timestamps()["btc"][60] == base + 60

    node_cache.append("btc", 60, base + 197, {"v": 3})
    assert node_cache.missing_flags()["btc"][60] is True
    assert node_cache.last_timestamps()["btc"][60] == base + 180

    # Out-of-order (older) data should clear the missing flag but preserve the last timestamp.
    node_cache.append("btc", 60, base + 15, {"v": "late"})
    assert node_cache.missing_flags()["btc"][60] is False
    assert node_cache.last_timestamps()["btc"][60] == base + 180
    window = node_cache.get_slice("btc", 60, count=3)
    assert {ts for ts, _ in window} == {base, base + 60, base + 180}
    assert window[-1] == (base, {"v": "late"})


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_arrow_backend_matches_tensor_semantics(monkeypatch):
    """Arrow cache backend mirrors NodeCache window semantics when enabled."""

    monkeypatch.setenv("QMTL_ARROW_CACHE", "1")
    cache = arrow_cache.NodeCacheArrow(period=2)
    try:
        cache.append("btc", 60, 60, {"v": 1})
        cache.append("btc", 60, 120, {"v": 2})
        cache.append("eth", 300, 300, {"v": 3})
        cache.append("eth", 300, 600, {"v": 4})

        assert cache.ready() is True
        view = cache.view()
        assert view["btc"][60].latest() == (120, {"v": 2})
        assert list(view["eth"][300]) == [(300, {"v": 3}), (600, {"v": 4})]

        cache.append("btc", 60, 300, {"v": 5})
        assert list(view["btc"][60])[-2:] == [(120, {"v": 2}), (300, {"v": 5})]

        cache.append("btc", 60, 420, {"v": 6})
        assert cache.missing_flags()["btc"][60] is True

        cache.append("btc", 60, 150, {"v": "late"})
        assert cache.missing_flags()["btc"][60] is False
    finally:
        cache.close()
        monkeypatch.delenv("QMTL_ARROW_CACHE", raising=False)
