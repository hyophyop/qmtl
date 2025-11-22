from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from qmtl.foundation.kafka import Producer
from qmtl.runtime.sdk import Node


class Pipeline:
    """Simple in-process execution pipeline for ``Node`` graphs."""

    def __init__(
        self,
        nodes: List[Node],
        *,
        producer: Optional[Producer] = None,
        feed_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.nodes = nodes
        self.producer = producer
        self._feed_fn: Callable[..., Any] | None = feed_fn
        self.downstream: Dict[Node, List[Node]] = {n: [] for n in nodes}
        for node in nodes:
            for inp in node.inputs:
                self.downstream.setdefault(inp, []).append(node)

    # ------------------------------------------------------------------
    def _publish(self, node: Node, interval: int, timestamp: int, payload: Any) -> None:
        if self.producer and node.kafka_topic:
            self.producer.produce(
                node.kafka_topic, {"interval": interval, "timestamp": timestamp, "payload": payload}
            )

    def _propagate(
        self,
        node: Node,
        interval: int,
        timestamp: int,
        payload: Any,
        *,
        on_missing: str = "skip",
    ) -> None:
        feed_fn = self._feed_fn
        if feed_fn is None:
            from qmtl.runtime.sdk.runner import Runner

            feed_fn = Runner.feed_queue_data
        for child in self.downstream.get(node, []):
            result = feed_fn(
                child,
                node.node_id,
                interval,
                timestamp,
                payload,
                on_missing=on_missing,
            )
            out = payload if not child.execute or child.compute_fn is None else result
            if out is None:
                continue
            self._publish(child, child.interval or interval, timestamp, out)
            self._propagate(
                child,
                child.interval or interval,
                timestamp,
                out,
                on_missing=on_missing,
            )

    # ------------------------------------------------------------------
    def feed(
        self, node: Node, timestamp: int, payload: Any, *, on_missing: str = "skip"
    ) -> None:
        """Feed ``payload`` into ``node`` and propagate through the graph."""
        interval = node.interval or 0
        node.feed(node.node_id, interval, timestamp, payload)
        self._publish(node, interval, timestamp, payload)
        self._propagate(node, interval, timestamp, payload, on_missing=on_missing)
