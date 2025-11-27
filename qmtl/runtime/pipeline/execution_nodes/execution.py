"""Execution simulation nodes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping, cast

from qmtl.runtime.sdk.execution_modeling import (
    ExecutionFill,
    ExecutionModel,
    MarketData,
    OrderSide,
    OrderType as ExecOrderType,
)
from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode

from ._shared import latest_entry
from qmtl.runtime.pipeline.order_types import ExecutionFillPayload, SizedOrder


class ExecutionNode(ProcessingNode):
    """Simulate execution using :class:`~qmtl.runtime.sdk.execution_modeling.ExecutionModel`."""

    def __init__(
        self,
        order: Node,
        *,
        execution_model: ExecutionModel | None = None,
        name: str | None = None,
    ) -> None:
        self.order = order
        self.execution_model = execution_model
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_exec",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> ExecutionFillPayload | SizedOrder | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        ts, order = latest
        if self.execution_model is None:
            return cast(SizedOrder, dict(order))
        price = float(order["price"])
        qty = float(order["quantity"])
        side = OrderSide.BUY if qty >= 0 else OrderSide.SELL
        market = MarketData(timestamp=ts, bid=price, ask=price, last=price, volume=abs(qty))
        fill = self.execution_model.simulate_execution(
            order_id=order.get("order_id", "order"),
            symbol=order["symbol"],
            side=side,
            quantity=abs(qty),
            order_type=ExecOrderType.MARKET,
            requested_price=price,
            market_data=market,
            timestamp=ts,
        )
        return cast(ExecutionFillPayload, asdict(fill))
