"""Execution-layer node wrappers.

This module provides reusable nodes for the execution layer of a strategy
pipeline. The nodes mirror the design described in
`docs/architecture/exchange_node_sets.md` and are intended to be composed
behind a signal node.

Currently includes:
- :class:`PreTradeGateNode`
- :class:`SizingNode`
"""

from __future__ import annotations

from typing import Mapping

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
from qmtl.sdk.pretrade import check_pretrade, Activation
from qmtl.common.pretrade import RejectionReason
from qmtl.brokerage import BrokerageModel, Account, OrderType, TimeInForce
from qmtl.sdk.portfolio import (
    Portfolio,
    order_value,
    order_percent,
    order_target_percent,
)


class PreTradeGateNode(Node):
    """Gate order intents using activation and brokerage checks.

    The node passes through valid orders or returns a structured rejection
    reason when blocked. See ``docs/architecture/exchange_node_sets.md`` for
    design details.
    """

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
            input=order,
            compute_fn=self._compute,
            name=name or f"{order.name}_pretrade",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        order = data[-1][1]
        result = check_pretrade(
            activation_map=self.activation_map,
            brokerage=self.brokerage,
            account=self.account,
            symbol=order["symbol"],
            quantity=order["quantity"],
            price=order.get("price", 0.0),
            order_type=order.get("order_type", OrderType.MARKET),
            tif=order.get("tif", TimeInForce.DAY),
            limit_price=order.get("limit_price"),
            stop_price=order.get("stop_price"),
        )
        if result.allowed:
            return order
        reason = result.reason.value if result.reason else RejectionReason.UNKNOWN.value
        return {"rejected": True, "reason": reason}


class SizingNode(Node):
    """Size order intents using portfolio helpers.

    Orders may specify one of ``quantity``, ``value``, ``percent``, or
    ``target_percent``. If ``quantity`` is provided, the order is passed
    through unchanged. Otherwise, the appropriate helper from
    :mod:`qmtl.sdk.portfolio` is used to compute the quantity based on the
    provided portfolio snapshot. See ``docs/architecture/exchange_node_sets.md``
    for design details.
    """

    def __init__(
        self,
        intent: Node,
        portfolio: Node,
        *,
        name: str | None = None,
    ) -> None:
        self.intent = intent
        self.portfolio = portfolio
        super().__init__(
            input=[intent, portfolio],
            compute_fn=self._compute,
            name=name or f"{intent.name}_sizing",
            interval=intent.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        intent_data = view[self.intent][self.intent.interval]
        portfolio_data = view[self.portfolio][self.portfolio.interval]
        if not intent_data or not portfolio_data:
            return None
        order = dict(intent_data[-1][1])
        _, portfolio = portfolio_data[-1]
        if "quantity" in order:
            return order
        price = order.get("price")
        if price is None:
            return None
        if "value" in order:
            qty = order_value(order["symbol"], order["value"], price)
        elif "percent" in order:
            qty = order_percent(portfolio, order["symbol"], order["percent"], price)
        elif "target_percent" in order:
            qty = order_target_percent(portfolio, order["symbol"], order["target_percent"], price)
        else:
            return order
        order["quantity"] = qty
        return order


__all__ = ["PreTradeGateNode", "SizingNode"]
