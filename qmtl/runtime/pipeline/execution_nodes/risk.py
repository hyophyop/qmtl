"""Risk control nodes."""

from __future__ import annotations

from typing import Any, Mapping, cast

from qmtl.runtime.sdk.node import CacheView, Node, ProcessingNode
from qmtl.runtime.sdk.portfolio import Portfolio
from qmtl.runtime.sdk.risk_management import PositionInfo, RiskManager

from ._shared import latest_entry
from qmtl.runtime.pipeline.order_types import RiskRejection, SizedOrder


class RiskControlNode(ProcessingNode):
    """Adjust or reject orders based on :class:`RiskManager` checks."""

    def __init__(
        self,
        order: Node,
        *,
        portfolio: Portfolio,
        risk_manager: RiskManager,
        name: str | None = None,
    ) -> None:
        self.order = order
        self.portfolio = portfolio
        self.risk_manager = risk_manager
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_risk",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> SizedOrder | RiskRejection | None:
        latest = latest_entry(view, self.order)
        if latest is None:
            return None
        _, order = latest
        current_positions = {
            sym: PositionInfo(
                symbol=sym,
                quantity=p.quantity,
                market_value=p.market_value,
                unrealized_pnl=p.unrealized_pnl,
                entry_price=p.avg_cost,
                current_price=p.market_price,
            )
            for sym, p in self.portfolio.positions.items()
        }
        ok, violation, adj_qty = self.risk_manager.validate_position_size(
            order["symbol"],
            float(order["quantity"]),
            float(order["price"]),
            self.portfolio.total_value,
            current_positions,
        )
        order = dict(order)
        if adj_qty and adj_qty != order["quantity"]:
            order["quantity"] = adj_qty
        if ok:
            return cast(SizedOrder, order)
        violation_reason = violation.violation_type.value if violation is not None else "unknown"
        return cast(RiskRejection, {"rejected": True, "violation": violation_reason})
