from __future__ import annotations

"""Position-intent emitting nodes for intent-first execution.

These nodes keep strategy logic pure by declaring target positions instead of
issuing imperative orders. Downstream execution can reconcile to targets using
portfolio snapshots (backtest) or world-level rebalancing (live).
"""

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node, ProcessingNode
from qmtl.runtime.sdk.intent import PositionTarget, to_order_payloads


@dataclass
class Thresholds:
    long_enter: float
    short_enter: float
    long_exit: float | None = None
    short_exit: float | None = None


def _hysteresis(prev: float | None, value: float, th: Thresholds) -> float:
    # Map continuous value to discrete {-1,0,+1} with hysteresis
    if prev is None or prev == 0:
        if value >= th.long_enter:
            return 1.0
        if value <= th.short_enter:
            return -1.0
        return 0.0
    if prev > 0:
        # stay long until exit falls below long_exit (if provided)
        if th.long_exit is not None and value < th.long_exit:
            return 0.0
        if value <= th.short_enter:
            return -1.0
        return 1.0  # remain long unless inversion
    # prev < 0
    if th.short_exit is not None and value > th.short_exit:
        return 0.0
    if value >= th.long_enter:
        return 1.0
    return -1.0


class PositionTargetNode(ProcessingNode):
    """Emit per-symbol position targets as intents.

    - Input is a stream whose latest payload is a float-like signal (alpha)
      for a single symbol.
    - Output is a :class:`PositionTarget` intent, or an order-shaped dict via
      ``to_order=True`` that carries ``target_percent`` for compatibility with
      sizing nodes.
    """

    def __init__(
        self,
        signal: Node,
        *,
        symbol: str,
        thresholds: Thresholds,
        long_weight: float = 1.0,
        short_weight: float = -1.0,
        hold_weight: float = 0.0,
        to_order: bool = True,
        price_node: Node | None = None,
        price_resolver: Callable[[CacheView], float | None] | None = None,
        name: str | None = None,
    ) -> None:
        self.signal = signal
        self.symbol = symbol
        self.thresholds = thresholds
        self.long_weight = float(long_weight)
        self.short_weight = float(short_weight)
        self.hold_weight = float(hold_weight)
        self.to_order = to_order
        if price_node is not None and price_resolver is not None:
            raise ValueError("provide only one of price_node or price_resolver")
        if to_order and price_node is None and price_resolver is None:
            raise ValueError(
                "price_node or price_resolver is required when to_order=True"
            )
        self.price_node = price_node
        self.price_resolver = price_resolver
        self._last_state: float | None = None
        super().__init__(
            signal,
            compute_fn=self._compute,
            name=name or f"{signal.name}_position_intent",
            interval=signal.interval,
            period=1,
        )

    def _compute(self, view: CacheView):
        data = view[self.signal][self.signal.interval]
        if not data:
            return None
        _, value = data[-1]
        try:
            x = float(value)
        except Exception:
            return None

        state = _hysteresis(self._last_state, x, self.thresholds)
        if state == self._last_state:
            # idempotent emission; avoid churn
            return None
        self._last_state = state

        target_percent = (
            self.long_weight if state > 0 else self.short_weight if state < 0 else self.hold_weight
        )
        intent = PositionTarget(symbol=self.symbol, target_percent=target_percent)
        if self.to_order:
            price = self._resolve_price(view)
            return to_order_payloads([intent], price_by_symbol={self.symbol: price})[0]
        return intent

    def _resolve_price(self, view: CacheView) -> float:
        if self.price_resolver is not None:
            price = self.price_resolver(view)
            if price is None:
                raise ValueError(
                    f"price_resolver returned None for symbol {self.symbol!r}"
                )
            try:
                return float(price)
            except Exception as exc:  # pragma: no cover - defensive guard
                raise ValueError(
                    f"price_resolver returned non-numeric value for symbol {self.symbol!r}"
                ) from exc

        if self.price_node is not None:
            data = view[self.price_node][self.price_node.interval]
            if not data:
                raise ValueError(
                    f"no price data available from {self.price_node.name!r} for symbol {self.symbol!r}"
                )
            _, value = data[-1]
            try:
                return float(value)
            except Exception as exc:  # pragma: no cover - defensive guard
                raise ValueError(
                    f"price stream {self.price_node.name!r} produced non-numeric value for symbol {self.symbol!r}"
                ) from exc

        raise ValueError("price source is not configured")


__all__ = ["PositionTargetNode", "Thresholds"]

