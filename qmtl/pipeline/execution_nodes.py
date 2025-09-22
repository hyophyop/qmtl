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
from typing import Mapping, Callable, Any

from qmtl.sdk.node import Node, ProcessingNode, StreamInput, CacheView
from qmtl.sdk.order_gate import Activation
from qmtl.sdk.watermark import WatermarkGate, is_ready
from qmtl.brokerage import BrokerageModel, Account
from qmtl.sdk.portfolio import (
    Portfolio,
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
from qmtl.sdk import metrics as sdk_metrics
from qmtl.dagmanager.kafka_admin import compute_key
from qmtl.gateway.commit_log import CommitLogWriter
import asyncio
from qmtl.transforms.execution_nodes import activation_blocks_order
from qmtl.transforms.execution_shared import run_pretrade_checks, apply_sizing


class PreTradeGateNode(ProcessingNode):
    """Gate orders using ``check_pretrade`` from :mod:`qmtl.sdk.pretrade`."""

    def __init__(
        self,
        order: Node,
        *,
        activation_map: Mapping[str, Activation],
        brokerage: BrokerageModel,
        account: Account,
        backpressure_guard: Callable[[], bool] | None = None,
        require_portfolio_watermark: bool | WatermarkGate | Mapping[str, Any] | None = False,
        watermark_gate: WatermarkGate | Mapping[str, Any] | bool | None = None,
        name: str | None = None,
    ) -> None:
        self.order = order
        self.activation_map = activation_map
        self.brokerage = brokerage
        self.account = account
        self.backpressure_guard = backpressure_guard
        self.watermark_gate = self._normalise_watermark_gate(
            watermark_gate if watermark_gate is not None else require_portfolio_watermark
        )
        self.require_portfolio_watermark = self.watermark_gate.enabled
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_pretrade",
            interval=order.interval,
            period=1,
        )

    @staticmethod
    def _normalise_watermark_gate(
        gate: WatermarkGate | Mapping[str, Any] | bool | None
    ) -> WatermarkGate:
        if isinstance(gate, WatermarkGate):
            return gate
        if isinstance(gate, bool) or gate is None:
            return WatermarkGate(enabled=bool(gate)) if gate else WatermarkGate(enabled=False)
        if isinstance(gate, Mapping):
            return WatermarkGate(**gate)
        raise TypeError("Unsupported watermark gate configuration")

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        ts, order = data[-1]
        # Optional backpressure guard: deny early if overloaded
        if self.backpressure_guard is not None:
            try:
                if self.backpressure_guard():
                    return {"rejected": True, "reason": "backpressure"}
            except Exception:
                pass
        # Optional watermark gating: require portfolio snapshot up to t-1
        if self.watermark_gate.enabled:
            try:
                interval = self.order.interval or 0
                if interval:
                    world = getattr(self.order, "world_id", None) or "default"
                    required = self.watermark_gate.required_timestamp(ts, interval)
                    if not is_ready(self.watermark_gate.topic, world, required):
                        return {"rejected": True, "reason": "watermark"}
            except Exception:
                pass

        _allowed, payload = run_pretrade_checks(
            order,
            activation_map=self.activation_map,
            brokerage=self.brokerage,
            account=self.account,
        )
        return payload


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
        return apply_sizing(order, self.portfolio, weight_fn=self.weight_fn)

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


class OrderPublishNode(ProcessingNode):
    """Publish orders to Gateway or commit log and pass them downstream."""

    def __init__(
        self,
        order: Node,
        *,
        commit_log_writer: CommitLogWriter | None = None,
        submit_order: Callable[[dict], None] | None = None,
        name: str | None = None,
    ) -> None:
        self.order = order
        self.commit_log_writer = commit_log_writer
        self.submit_order = submit_order
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_publish",
            interval=order.interval,
            period=1,
        )

    def _publish_commit_log(self, ts: int, order: dict) -> None:
        if self.commit_log_writer is None:
            return
        try:
            def _ctx(name: str) -> str | None:
                for source in (self, self.order):
                    value = getattr(source, name, None)
                    if value is not None:
                        return str(value)
                return None

            key_hint = compute_key(
                self.node_id,
                world_id=_ctx("world_id"),
                execution_domain=_ctx("execution_domain"),
                as_of=_ctx("as_of"),
                partition=_ctx("partition"),
                dataset_fingerprint=_ctx("dataset_fingerprint"),
            )
            coro = self.commit_log_writer.publish_bucket(
                ts,
                self.order.interval,
                [(self.node_id, "", order, key_hint)],
            )
            try:
                asyncio.get_running_loop().create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
        except Exception:
            pass

    def _publish_gateway(self, order: dict) -> None:
        if self.submit_order is None:
            return
        try:
            self.submit_order(order)
        except Exception:
            pass

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        ts, order = data[-1]
        if activation_blocks_order(order):
            return order
        self._publish_commit_log(ts, order)
        self._publish_gateway(order)
        try:
            sdk_metrics.record_order_published()
        except Exception:
            pass
        return order

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

    def __init__(
        self,
        fills: Node,
        *,
        portfolio: Portfolio,
        name: str | None = None,
        watermark_topic: str | None = "trade.portfolio",
    ) -> None:
        self.fills = fills
        self.portfolio = portfolio
        self._watermark_topic = watermark_topic
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
        ts, fill = data[-1]
        try:
            sdk_metrics.record_fill_ingested()
        except Exception:
            pass
        symbol = fill["symbol"]
        qty = float(fill["quantity"])
        price = float(fill.get("fill_price", fill.get("price", 0.0)))
        commission = float(fill.get("commission", 0.0))
        self.portfolio.apply_fill(symbol, qty, price, commission)
        # Update watermark for portfolio snapshots
        if self._watermark_topic:
            try:
                from qmtl.sdk.watermark import set_watermark

                world = getattr(self.fills, "world_id", None) or "default"
                fill_ts = (
                    int(fill.get("timestamp", ts)) if isinstance(fill, dict) else int(ts)
                )
                set_watermark(self._watermark_topic, world, fill_ts)
            except Exception:
                pass
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
    "OrderPublishNode",
    "FillIngestNode",
    "PortfolioNode",
    "RiskControlNode",
    "TimingGateNode",
]
