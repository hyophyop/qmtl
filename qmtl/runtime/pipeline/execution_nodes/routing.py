"""Order routing nodes."""

from __future__ import annotations

from typing import Callable, Mapping, Any

from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode

from ._shared import latest_entry


class RouterNode(ProcessingNode):
    """Route orders to a target based on a user-provided function."""

    def __init__(
        self,
        order: Node,
        *,
        route_fn: Callable[[Mapping[str, Any]], Any],
        name: str | None = None,
    ) -> None:
        if not callable(route_fn):
            raise ValueError("route_fn must be callable")
        self.order = order
        self.route_fn = route_fn
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_router",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView[Mapping[str, Any]]) -> dict | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        _, order = latest
        route = self.route_fn(order)
        out = dict(order)
        out["route"] = route
        return out
