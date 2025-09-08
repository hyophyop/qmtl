from __future__ import annotations

from qmtl.sdk.node import ProcessingNode, Node, CacheView


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
    """

    def __init__(self, order: Node, *, name: str | None = None) -> None:
        self.order = order
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

    def __init__(self, fills: Node, *, name: str | None = None) -> None:
        self.fills = fills
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
    "StubFillIngestNode",
    "StubPortfolioNode",
    "StubRiskControlNode",
    "StubTimingGateNode",
]

