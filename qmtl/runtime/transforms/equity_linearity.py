"""Node adapters for equity curve linearity metrics.

The pure metric helpers live in :mod:`qmtl.runtime.transforms.linearity_metrics`.
This module re-exports the metric functions for backwards compatibility
while providing the node factories used throughout the SDK.
"""

from __future__ import annotations

from collections.abc import Sequence

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .linearity_metrics import equity_linearity_metrics, equity_linearity_metrics_v2

__all__ = [
    "equity_linearity_metrics",
    "equity_linearity_from_history_node",
    "equity_linearity_metrics_v2",
    "equity_linearity_v2_from_history_node",
]


def equity_linearity_from_history_node(
    history: Node,
    *,
    name: str | None = None,
    eps: float = 1e-12,
) -> Node:
    """Wrap :func:`equity_linearity_metrics` for a history-producing node."""

    def compute(view: CacheView):
        data = view[history][history.interval]
        if not data:
            return None
        series = data[-1][1]
        return equity_linearity_metrics(series, eps=eps)

    return Node(
        input=history,
        compute_fn=compute,
        name=name or f"{history.name}_equity_linearity",
        interval=history.interval,
        period=history.period,
    )


def equity_linearity_v2_from_history_node(
    history: Node,
    *,
    name: str | None = None,
    orientation: str = "up",
    eps: float = 1e-10,
    use_log: bool = False,
    scales: Sequence[int] = (1, 5, 20),
) -> Node:
    """Node wrapper for :func:`equity_linearity_metrics_v2`."""

    def compute(view: CacheView):
        data = view[history][history.interval]
        if not data:
            return None
        series = data[-1][1]
        return equity_linearity_metrics_v2(
            series,
            orientation=orientation,
            eps=eps,
            use_log=use_log,
            scales=scales,
        )

    return Node(
        input=history,
        compute_fn=compute,
        name=name or f"{history.name}_equity_linearity_v2",
        interval=history.interval,
        period=history.period,
    )
