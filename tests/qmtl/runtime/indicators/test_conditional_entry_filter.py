"""Tests for the ``conditional_entry_filter`` microstructure utility."""

from __future__ import annotations

from qmtl.runtime.indicators import (
    conditional_entry_filter,
    microprice_imbalance,
    priority_index,
)
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import SourceNode


def _view_for(source: SourceNode, snapshot: dict) -> CacheView:
    return CacheView({source.node_id: {source.interval: [(0, snapshot)]}})


def _gate_view(micro_node, micro_payload, priority_node, priority_payload) -> CacheView:
    return CacheView(
        {
            micro_node.node_id: {micro_node.interval: [(0, micro_payload)]},
            priority_node.node_id: {priority_node.interval: [(0, priority_payload)]},
        }
    )


def test_conditional_entry_filter_accepts_balanced_queue() -> None:
    book_source = SourceNode(interval="1s", period=5)
    queue_source = SourceNode(interval="1s", period=5)

    micro_node = microprice_imbalance(book_source, top_levels=2)
    priority_node = priority_index(queue_source)
    gate = conditional_entry_filter(micro_node, priority_node)

    book_snapshot = {
        "bids": [(100.0, 4.0), (99.5, 3.5)],
        "asks": [(100.5, 3.5), (101.0, 3.0)],
    }
    queue_snapshot = {"queue_rank": 1, "queue_size": 5}

    micro_payload = micro_node.compute_fn(_view_for(book_source, book_snapshot))
    priority_payload = priority_node.compute_fn(_view_for(queue_source, queue_snapshot))

    result = gate.compute_fn(_gate_view(micro_node, micro_payload, priority_node, priority_payload))

    assert result is True


def test_conditional_entry_filter_rejects_out_of_bounds_imbalance() -> None:
    book_source = SourceNode(interval="1s", period=5)
    queue_source = SourceNode(interval="1s", period=5)

    micro_node = microprice_imbalance(book_source, top_levels=1)
    priority_node = priority_index(queue_source)
    gate = conditional_entry_filter(
        micro_node,
        priority_node,
        imbalance_bounds=(-0.1, 0.1),
    )

    book_snapshot = {
        "bids": [(100.0, 6.0)],
        "asks": [(100.5, 1.0)],
    }
    queue_snapshot = {"queue_rank": 0, "queue_size": 5}

    micro_payload = micro_node.compute_fn(_view_for(book_source, book_snapshot))
    priority_payload = priority_node.compute_fn(_view_for(queue_source, queue_snapshot))

    result = gate.compute_fn(_gate_view(micro_node, micro_payload, priority_node, priority_payload))

    assert result is False


def test_conditional_entry_filter_enforces_priority_mode_all() -> None:
    book_source = SourceNode(interval="1s", period=5)
    queue_source = SourceNode(interval="1s", period=5)

    micro_node = microprice_imbalance(book_source)
    priority_node = priority_index(queue_source)
    gate = conditional_entry_filter(
        micro_node,
        priority_node,
        priority_bounds=(0.5, 1.0),
        priority_mode="all",
    )

    book_snapshot = {
        "bids": [(100.0, 4.0)],
        "asks": [(100.5, 4.0)],
    }
    queue_snapshot = {
        "queue_rank": [0, 3],
        "queue_size": [5, 5],
    }

    micro_payload = micro_node.compute_fn(_view_for(book_source, book_snapshot))
    priority_payload = priority_node.compute_fn(_view_for(queue_source, queue_snapshot))

    result = gate.compute_fn(_gate_view(micro_node, micro_payload, priority_node, priority_payload))

    assert result is False
