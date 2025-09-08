"""Micro-batching helpers for order publish and fill ingest.

These nodes aggregate all items in the latest time bucket from an upstream
``Node`` and emit them as a list to reduce per-item overhead.
"""

from __future__ import annotations

from typing import Any

from qmtl.sdk.node import ProcessingNode, Node
from qmtl.sdk.cache_view import CacheView


class MicroBatchNode(ProcessingNode):
    """Aggregate upstream payloads for the latest timestamp into a list."""

    def __init__(self, upstream: Node, *, name: str | None = None) -> None:
        self.upstream = upstream
        super().__init__(
            upstream,
            compute_fn=self._compute,
            name=name or f"{upstream.name}_mbatch",
            interval=upstream.interval,
            period=upstream.period or 1,
        )

    def _compute(self, view: CacheView) -> list[Any] | None:
        data = view[self.upstream][self.upstream.interval]
        # Convert CacheView leaf to a plain list via slicing
        seq = data[:] if data else []
        if not seq:
            return None
        # Identify distinct timestamps (ordered as in seq)
        timestamps = [ts for ts, _ in seq]
        distinct = []
        for ts in timestamps:
            if not distinct or distinct[-1] != ts:
                distinct.append(ts)
        # Flush the latest complete bucket: the second-to-last distinct ts
        if len(distinct) < 2:
            return None
        flush_ts = distinct[-2]
        batch: list[Any] = [payload for ts, payload in seq if ts == flush_ts]
        return batch


__all__ = ["MicroBatchNode"]
