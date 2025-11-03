"""Example pipeline combining microprice imbalance and priority index."""

from __future__ import annotations

from dataclasses import dataclass

from qmtl.runtime.indicators import (
    conditional_entry_filter,
    microprice_imbalance,
    priority_index,
)
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node, SourceNode


@dataclass(slots=True)
class PipelineArtifacts:
    """Bundle of nodes composing the microstructure example pipeline."""

    order_book: SourceNode
    queue_metadata: SourceNode
    microprice_metrics: Node
    priority: Node
    entry_gate: Node


def build_pipeline() -> PipelineArtifacts:
    """Build nodes wiring microprice/imbalance into a simple gate."""

    order_book = SourceNode(interval="1s", period=5, config={"id": "order_book"})
    queue_metadata = SourceNode(interval="1s", period=5, config={"id": "queue"})

    microprice_metrics = microprice_imbalance(order_book, top_levels=3)
    priority = priority_index(queue_metadata)
    entry_gate = conditional_entry_filter(
        microprice_metrics,
        priority,
        imbalance_bounds=(-0.2, 0.2),
        priority_bounds=(0.6, 1.0),
    )

    return PipelineArtifacts(
        order_book=order_book,
        queue_metadata=queue_metadata,
        microprice_metrics=microprice_metrics,
        priority=priority,
        entry_gate=entry_gate,
    )


def simulate_single_snapshot() -> dict[str, object]:
    """Run the pipeline with mocked data and return the emitted metrics."""

    artifacts = build_pipeline()
    order_snapshot = {
        "bids": [(100.0, 4.0), (99.9, 2.5), (99.8, 2.0)],
        "asks": [(100.1, 3.0), (100.2, 2.5), (100.3, 1.5)],
    }
    queue_snapshot = {"queue_rank": 2, "queue_size": 10}

    order_view = CacheView(
        {
            artifacts.order_book.node_id: {
                artifacts.order_book.interval: [(0, order_snapshot)]
            }
        }
    )
    micro_metrics = artifacts.microprice_metrics.compute_fn(order_view)

    queue_view = CacheView(
        {
            artifacts.queue_metadata.node_id: {
                artifacts.queue_metadata.interval: [(0, queue_snapshot)]
            }
        }
    )
    priority_value = artifacts.priority.compute_fn(queue_view)

    gate_view = CacheView(
        {
            artifacts.microprice_metrics.node_id: {
                artifacts.microprice_metrics.interval: [(0, micro_metrics)]
            },
            artifacts.priority.node_id: {
                artifacts.priority.interval: [(0, priority_value)]
            },
        }
    )
    allow_entry = artifacts.entry_gate.compute_fn(gate_view)

    return {
        "microprice": None if micro_metrics is None else micro_metrics.get("microprice"),
        "imbalance": None if micro_metrics is None else micro_metrics.get("imbalance"),
        "priority_index": priority_value,
        "allow_entry": allow_entry,
    }


def main() -> None:
    """Print the simulated outputs for quick inspection."""

    snapshot = simulate_single_snapshot()
    for key, value in snapshot.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
