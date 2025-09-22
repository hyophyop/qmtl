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

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
from qmtl.sdk.pretrade import Activation
from qmtl.brokerage import BrokerageModel, Account
from qmtl.sdk.portfolio import Portfolio
from qmtl.transforms.execution_shared import run_pretrade_checks, apply_sizing


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
        order = intent_data[-1][1]
        _, portfolio = portfolio_data[-1]
        return apply_sizing(order, portfolio)


def _infer_activation_side(order: Mapping[str, Any]) -> str | None:
    """Infer order side for activation gating."""

    side = order.get("side")
    if side is not None:
        s = str(side).lower()
        if s in {"buy", "long"}:
            return "buy"
        if s in {"sell", "short"}:
            return "sell"

    qty = order.get("quantity")
    if qty is not None:
        try:
            return "buy" if float(qty) >= 0 else "sell"
        except (TypeError, ValueError):
            pass

    for key in ("value", "percent", "target_percent"):
        val = order.get(key)
        if val is not None:
            try:
                return "buy" if float(val) >= 0 else "sell"
            except (TypeError, ValueError):
                continue
    return None


def activation_blocks_order(order: Mapping[str, Any]) -> bool:
    """Return ``True`` when the global ActivationManager gates the order."""

    try:
        from qmtl.sdk.runner import Runner  # Late import to avoid cycle
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
