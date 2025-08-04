from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Dict, List, Optional

from qmtl.kafka import Producer
from qmtl.sdk import Node
from qmtl.sdk.runner import Runner


class Pipeline:
    """Simple in-process execution pipeline for ``Node`` graphs."""

    def __init__(self, nodes: List[Node], *, producer: Optional[Producer] = None) -> None:
        self.nodes = nodes
        self.producer = producer
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

    async def _propagate(
        self,
        node: Node,
        interval: int,
        timestamp: int,
        payload: Any,
        *,
        on_missing: str = "skip",
    ) -> None:
        queue: deque[tuple[Node, int, Any]] = deque([(node, interval, payload)])
        while queue:
            parent, cur_interval, cur_payload = queue.popleft()
            children = self.downstream.get(parent, [])
            if not children:
                continue
            tasks = [
                asyncio.to_thread(
                    Runner.feed_queue_data,
                    child,
                    parent.node_id,
                    cur_interval,
                    timestamp,
                    cur_payload,
                    on_missing=on_missing,
                )
                for child in children
            ]
            results = await asyncio.gather(*tasks)
            for child, result in zip(children, results):
                out = cur_payload if not child.execute or child.compute_fn is None else result
                if out is None:
                    continue
                child_interval = child.interval or cur_interval
                self._publish(child, child_interval, timestamp, out)
                queue.append((child, child_interval, out))

    # ------------------------------------------------------------------
    def feed(
        self, node: Node, timestamp: int, payload: Any, *, on_missing: str = "skip"
    ) -> None:
        """Feed ``payload`` into ``node`` and propagate through the graph."""
        interval = node.interval or 0
        node.feed(node.node_id, interval, timestamp, payload)
        self._publish(node, interval, timestamp, payload)
        asyncio.run(
            self._propagate(node, interval, timestamp, payload, on_missing=on_missing)
        )
