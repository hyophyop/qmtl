"""Order sizing nodes."""

from __future__ import annotations

from typing import Callable

from qmtl.sdk.node import CacheView, Node, ProcessingNode
from qmtl.sdk.portfolio import Portfolio

from qmtl.transforms.execution_shared import apply_sizing

from ._shared import latest_entry


class SizingNode(ProcessingNode):
    """Convert sizing instructions to absolute quantity."""

    def __init__(
        self,
        order: Node,
        *,
        portfolio: Portfolio,
        name: str | None = None,
        weight_fn: Callable[[dict], float] | None = None,
    ) -> None:
        self.order = order
        self.portfolio = portfolio
        self.weight_fn = weight_fn
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_sizing",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        _, order = latest
        return apply_sizing(order, self.portfolio, weight_fn=self.weight_fn)
