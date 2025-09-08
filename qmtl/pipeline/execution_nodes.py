"""Execution-layer node wrappers for strategy pipelines.

This module provides lightweight ``Node`` wrappers for common
execution-layer components such as pre-trade checks, sizing, execution
simulation, fill ingestion, portfolio updates and risk/timing gates.

Each node operates on simple dictionary payloads so strategies can compose
them with minimal boilerplate. The implementations intentionally keep the
logic thin by delegating to the helper functions under :mod:`qmtl.sdk`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Mapping, Callable

from qmtl.sdk.node import Node, ProcessingNode, StreamInput, CacheView
from qmtl.sdk.pretrade import check_pretrade
from qmtl.sdk.order_gate import Activation
from qmtl.brokerage import BrokerageModel, Account, OrderType, TimeInForce
from qmtl.sdk.portfolio import (
    Portfolio,
    order_percent,
    order_target_percent,
    order_value,
)
from qmtl.sdk.execution_modeling import (
    ExecutionModel,
    ExecutionFill,
    MarketData,
    OrderSide,
    OrderType as ExecOrderType,
)
from qmtl.sdk.risk_management import RiskManager, PositionInfo
from qmtl.sdk.timing_controls import TimingController


class PreTradeGateNode(ProcessingNode):
    """Gate orders using ``check_pretrade`` from :mod:`qmtl.sdk.pretrade`."""

    def __init__(
        self,
        order: Node,
        *,
        activation_map: Mapping[str, Activation],
        brokerage: BrokerageModel,
        account: Account,
        name: str | None = None,
    ) -> None:
        self.order = order
        self.activation_map = activation_map
        self.brokerage = brokerage
        self.account = account
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_pretrade",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        ts, order = data[-1]
        result = check_pretrade(
            activation_map=self.activation_map,
            brokerage=self.brokerage,
            account=self.account,
            symbol=order["symbol"],
            quantity=int(order["quantity"]),
            price=float(order["price"]),
            order_type=order.get("order_type", OrderType.MARKET),
            tif=order.get("tif", TimeInForce.DAY),
            limit_price=order.get("limit_price"),
            stop_price=order.get("stop_price"),
        )
        if result.allowed:
            return order
        return {"rejected": True, "reason": result.reason.value}


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
        data = view[self.order][self.order.interval]
        if not data:
            return None
        _, order = data[-1]
        if "quantity" in order:
            return order
        price = float(order["price"])
        symbol = order["symbol"]
        if "value" in order:
            qty = order_value(symbol, float(order["value"]), price)
        elif "percent" in order:
            qty = order_percent(self.portfolio, symbol, float(order["percent"]), price)
        elif "target_percent" in order:
            qty = order_target_percent(
                self.portfolio, symbol, float(order["target_percent"]), price
            )
        else:
            return order
        order = dict(order)
        # Apply soft gating weight if provided
        if self.weight_fn is not None:
            try:
                factor = float(self.weight_fn(order))
                if factor < 0.0:
                    factor = 0.0
                if factor > 1.0:
                    factor = 1.0
                qty *= factor
            except Exception:
                # Ignore weighting errors
                pass
        order["quantity"] = qty
        return order

class ExecutionNode(ProcessingNode):
    """Simulate execution using :class:`~qmtl.sdk.execution_modeling.ExecutionModel`."""

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

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        ts, order = data[-1]
        if self.execution_model is None:
            return order
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
        if isinstance(fill, ExecutionFill):
            return asdict(fill)
        return fill

class RouterNode(ProcessingNode):
    """Route orders to a target based on a user-provided function.

    The router adds a `route` field to the order payload. Downstream nodes can
    branch based on this field to direct orders to the appropriate exchange or
    connector.
    """

    def __init__(self, order: Node, *, route_fn: callable, name: str | None = None) -> None:
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

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        _, order = data[-1]
        route = self.route_fn(order)
        out = dict(order)
        out["route"] = route
        return out

class FillIngestNode(StreamInput):
    """Stream node for external execution fills."""

    def __init__(self, *, name: str | None = None, interval: int | None = None) -> None:
        super().__init__(name=name or "fill_ingest", interval=interval, period=1)


class PortfolioNode(ProcessingNode):
    """Apply fills to a :class:`~qmtl.sdk.portfolio.Portfolio`."""

    def __init__(self, fills: Node, *, portfolio: Portfolio, name: str | None = None) -> None:
        self.fills = fills
        self.portfolio = portfolio
        super().__init__(
            fills,
            compute_fn=self._compute,
            name=name or f"{fills.name}_portfolio",
            interval=fills.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.fills][self.fills.interval]
        if not data:
            return None
        _, fill = data[-1]
        symbol = fill["symbol"]
        qty = float(fill["quantity"])
        price = float(fill.get("fill_price", fill.get("price", 0.0)))
        commission = float(fill.get("commission", 0.0))
        self.portfolio.apply_fill(symbol, qty, price, commission)
        snapshot = {
            "cash": self.portfolio.cash,
            "positions": {
                sym: {"qty": p.quantity, "price": p.market_price}
                for sym, p in self.portfolio.positions.items()
            },
        }
        return snapshot


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

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        _, order = data[-1]
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
            return order
        return {"rejected": True, "violation": violation.violation_type.value}


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

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        ts, order = data[-1]
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        ok, reason, _ = self.controller.validate_timing(dt)
        if ok:
            return order
        return {"rejected": True, "reason": reason}


__all__ = [
    "PreTradeGateNode",
    "SizingNode",
    "ExecutionNode",
    "FillIngestNode",
    "PortfolioNode",
    "RiskControlNode",
    "TimingGateNode",
]
