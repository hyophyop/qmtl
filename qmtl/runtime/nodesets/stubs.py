from __future__ import annotations

from typing import Callable

from qmtl.runtime.sdk.node import ProcessingNode, Node, CacheView
from qmtl.runtime.sdk.portfolio import Portfolio


class StubPreTradeGateNode(ProcessingNode):
    """Pass-through pre-trade gate stub.

    This stub intentionally performs no checks; it exists to scaffold the
    execution chain without introducing dependencies.
    """

    def __init__(self, order: Node, *, name: str | None = None) -> None:
        self.order = order
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
        _, order = data[-1]
        return order


class StubSizingNode(ProcessingNode):
    """Pass-through sizing stub.

    A real implementation would convert value/percent to absolute quantity.
    The stub still records shared resources for compatibility with recipes.
    """

    def __init__(
        self,
        order: Node,
        *,
        portfolio: Portfolio | None = None,
        weight_fn: Callable[[dict], float] | None = None,
        name: str | None = None,
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
        return order


class StubExecutionNode(ProcessingNode):
    """Pass-through execution stub."""

    def __init__(self, order: Node, *, name: str | None = None) -> None:
        self.order = order
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
        _, order = data[-1]
        return order


class StubOrderPublishNode(ProcessingNode):
    """Pass-through order publish stub."""

    def __init__(self, order: Node, *, name: str | None = None) -> None:
        self.order = order
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_publish",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        _, order = data[-1]
        return order


class StubFillIngestNode(ProcessingNode):
    """Placeholder for a live fills stream; pass-through for scaffolding."""

    def __init__(self, order: Node, *, name: str | None = None) -> None:
        self.order = order
        super().__init__(
            order,
            compute_fn=self._compute,
            name=name or f"{order.name}_fills",
            interval=order.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.order][self.order.interval]
        if not data:
            return None
        _, order = data[-1]
        return order


class StubPortfolioNode(ProcessingNode):
    """Pass-through portfolio stub."""

    def __init__(
        self,
        fills: Node,
        *,
        portfolio: Portfolio | None = None,
        name: str | None = None,
    ) -> None:
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
        _, payload = data[-1]
        return payload


class StubRiskControlNode(ProcessingNode):
    """Pass-through risk control stub."""

    def __init__(self, order: Node, *, name: str | None = None) -> None:
        self.order = order
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
        return order


class StubTimingGateNode(ProcessingNode):
    """Pass-through timing gate stub."""

    def __init__(self, order: Node, *, name: str | None = None) -> None:
        self.order = order
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
        _, order = data[-1]
        return order


__all__ = [
    "StubPreTradeGateNode",
    "StubSizingNode",
    "StubExecutionNode",
    "StubOrderPublishNode",
    "StubFillIngestNode",
    "StubPortfolioNode",
    "StubRiskControlNode",
    "StubTimingGateNode",
]

