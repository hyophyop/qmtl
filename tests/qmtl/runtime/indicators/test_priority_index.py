"""Tests for the ``priority_index`` indicator node."""

from __future__ import annotations

import pytest

from qmtl.runtime.indicators import priority_index
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import SourceNode


def _view_for_snapshots(source: SourceNode, snapshots: list[dict]) -> CacheView:
    data = {
        source.node_id: {
            source.interval: [(idx, snapshot) for idx, snapshot in enumerate(snapshots)]
        }
    }
    return CacheView(data)


def test_priority_index_scalar_normalization() -> None:
    source = SourceNode(interval="1s", period=5)
    snapshot = {"queue_rank": 2, "queue_size": 10}
    node = priority_index(source)

    view = _view_for_snapshots(source, [snapshot])

    result = node.compute_fn(view)
    assert result == pytest.approx(0.8)


def test_priority_index_batched_normalization() -> None:
    source = SourceNode(interval="1s", period=5)
    snapshot = {"queue_rank": [0, 5, 10], "queue_size": [10, 10, 10]}
    node = priority_index(source)

    view = _view_for_snapshots(source, [snapshot])

    result = node.compute_fn(view)
    assert result == pytest.approx([1.0, 0.5, 0.0])


def test_priority_index_missing_queue_metadata_raises() -> None:
    source = SourceNode(interval="1s", period=5)
    snapshot = {"queue_rank": 1}
    node = priority_index(source)

    view = _view_for_snapshots(source, [snapshot])

    with pytest.raises(ValueError) as exc:
        node.compute_fn(view)

    assert "queue_size" in str(exc.value)


def test_priority_index_invalid_inputs_return_none() -> None:
    source = SourceNode(interval="1s", period=5)
    invalid_snapshot = {"queue_rank": 1, "queue_size": 0}
    node = priority_index(source)

    view = _view_for_snapshots(source, [invalid_snapshot])

    assert node.compute_fn(view) is None


def test_priority_index_batched_invalid_entry_returns_none_marker() -> None:
    source = SourceNode(interval="1s", period=5)
    snapshot = {"queue_rank": [0, 1], "queue_size": [5, 0]}
    node = priority_index(source)

    view = _view_for_snapshots(source, [snapshot])

    assert node.compute_fn(view) == [1.0, None]
