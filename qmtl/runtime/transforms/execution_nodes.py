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

from typing import Mapping, Any

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.pretrade import Activation
from qmtl.runtime.brokerage import BrokerageModel, Account
from qmtl.runtime.sdk.portfolio import Portfolio
from qmtl.runtime.transforms.execution_shared import run_pretrade_checks, apply_sizing
from qmtl.runtime.pipeline.order_types import OrderRejection, SizedOrder


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

    def _compute(self, view: CacheView) -> SizedOrder | OrderRejection | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        order = data[-1][1]
        _, payload = run_pretrade_checks(
            order,
            activation_map=self.activation_map,
            brokerage=self.brokerage,
            account=self.account,
        )
        return payload


class SizingNode(Node):
    """Size order intents using portfolio helpers.

    Orders may specify one of ``quantity``, ``value``, ``percent``, or
    ``target_percent``. If ``quantity`` is provided, the order is passed
    through unchanged. Otherwise, the appropriate helper from
    :mod:`qmtl.runtime.sdk.portfolio` is used to compute the quantity based on the
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

    def _compute(self, view: CacheView) -> SizedOrder | None:
        intent_data = view[self.intent][self.intent.interval]
        portfolio_data = view[self.portfolio][self.portfolio.interval]
        if not intent_data or not portfolio_data:
            return None
        order = intent_data[-1][1]
        _, portfolio = portfolio_data[-1]
        return apply_sizing(order, portfolio)


def _infer_activation_side(order: Mapping[str, Any]) -> str | None:
    """Infer order side for activation gating."""

    normalized_side = _normalize_side(order.get("side"))
    if normalized_side is not None:
        return normalized_side

    qty_based = _infer_by_numeric(order, ("quantity",))
    if qty_based is not None:
        return qty_based

    return _infer_by_numeric(order, ("value", "percent", "target_percent"))


def _normalize_side(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).lower()
    if s in {"buy", "long"}:
        return "buy"
    if s in {"sell", "short"}:
        return "sell"
    return None


def _infer_by_numeric(order: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        val = order.get(key)
        if val is None:
            continue
        try:
            return "buy" if float(val) >= 0 else "sell"
        except (TypeError, ValueError):
            continue
    return None


def activation_blocks_order(order: Mapping[str, Any]) -> bool:
    """Return ``True`` when the global ActivationManager gates the order."""

    try:
        from qmtl.runtime.sdk.runner import Runner  # Late import to avoid cycle
    except Exception:
        return False

    am = Runner.services().activation_manager
    if am is None:
        return False

    side = _infer_activation_side(order)
    if side is None:
        return False

    try:
        return not am.allow_side(side)
    except Exception:
        return False


__all__ = ["PreTradeGateNode", "SizingNode", "activation_blocks_order"]
