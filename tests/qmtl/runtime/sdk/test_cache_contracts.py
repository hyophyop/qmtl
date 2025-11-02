from __future__ import annotations

import pytest

from qmtl.runtime.sdk.node import NodeCache


def test_node_cache_buckets_timestamps_and_preserves_order() -> None:
    cache = NodeCache(period=3)

    cache.append("price", 60, 125, {"value": 1})
    cache.append("price", 60, 185, {"value": 2})

    snapshot = cache._snapshot()
    assert list(snapshot.keys()) == ["price"]
    entries = snapshot["price"][60]
    assert entries == [
        (120, {"value": 1}),
        (180, {"value": 2}),
    ]


def test_node_cache_reports_gaps_when_intervals_are_skipped() -> None:
    cache = NodeCache(period=2)

    cache.append("price", 60, 0, {"value": 1})
    cache.append("price", 60, 180, {"value": 2})

    flags = cache.missing_flags()
    assert flags == {"price": {60: True}}
    timestamps = cache.last_timestamps()
    assert timestamps == {"price": {60: 180}}


def test_node_cache_resets_when_compute_key_changes() -> None:
    cache = NodeCache(period=2)

    cache.activate_compute_key("key-1", node_id="node-1")
    cache.append("price", 60, 60, {"value": 1})
    assert cache._snapshot()["price"][60]

    cache.activate_compute_key("key-2", node_id="node-1")
    assert cache._snapshot() == {}

    cache.append("price", 60, 120, {"value": 2})
    snapshot = cache._snapshot()
    assert snapshot == {"price": {60: [(120, {"value": 2})]}}
