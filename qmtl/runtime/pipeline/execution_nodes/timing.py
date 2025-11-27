"""Timing control nodes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode
from qmtl.runtime.sdk.timing_controls import TimingController

from ._shared import latest_entry


class TimingGateNode(ProcessingNode):
    """Gate orders based on market timing rules."""

    def __init__(
        self, order: Node, *, controller: TimingController, name: str | None = None
    ) -> None:
        self.order = order
        self.controller = controller
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_timing",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView[Mapping[str, Any]]) -> dict[str, Any] | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        ts, order = latest
        order_payload = dict(order)
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        ok, reason, _ = self.controller.validate_timing(dt)
        if ok:
            return order_payload
        return {"rejected": True, "reason": reason}
