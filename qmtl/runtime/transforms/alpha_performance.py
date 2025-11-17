"""Compute performance metrics from alpha series."""

from collections.abc import Sequence
from typing import Optional

from qmtl.runtime.helpers import (
    adjust_returns_for_costs,
    calculate_execution_metrics,
)
from qmtl.runtime.helpers.runtime import compute_alpha_performance_summary
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.execution_modeling import ExecutionFill
from qmtl.runtime.sdk.node import Node


def alpha_performance_node(
    returns: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    transaction_cost: float = 0.0,
    execution_fills: Optional[Sequence[ExecutionFill]] = None,
    use_realistic_costs: bool = False,
) -> dict[str, float]:
    """Return key performance metrics from a return series.

    NaN values in ``returns`` are ignored. If all entries are NaN (or the
    sequence is empty), all metrics are ``0.0``. The Sharpe ratio is reported
    as ``0.0`` when the standard deviation of returns is zero.

    Parameters
    ----------
    returns:
        Sequence of periodic returns.
    risk_free_rate:
        Optional risk-free rate used when computing the Sharpe ratio.
    transaction_cost:
        Optional transaction cost subtracted from each return (simple model).
    execution_fills:
        Optional list of ExecutionFill objects for realistic cost modeling.
    use_realistic_costs:
        If True and execution_fills provided, use realistic execution costs.

    Returns
    -------
    dict[str, float]
        Mapping containing ``sharpe``, ``max_drawdown``, ``win_ratio``,
        ``profit_factor``, ``car_mdd``, ``rar_mdd`` and execution quality metrics.
    """

    result: dict[str, float] = compute_alpha_performance_summary(
        returns,
        risk_free_rate=risk_free_rate,
        transaction_cost=transaction_cost,
        execution_fills=execution_fills or (),
        use_realistic_costs=use_realistic_costs,
    )
    return result


def alpha_performance_from_history_node(
    history: Node,
    *,
    risk_free_rate: float = 0.0,
    transaction_cost: float = 0.0,
    name: str | None = None,
) -> Node:
    """Wrap :func:`alpha_performance_node` for a history-producing node.

    Parameters
    ----------
    history:
        Node emitting a sequence of alpha returns (e.g. from ``alpha_history_node``).
    risk_free_rate:
        Optional risk-free rate used when computing the Sharpe ratio.
    transaction_cost:
        Optional transaction cost subtracted from each return.
    name:
        Optional name for the resulting node.

    Returns
    -------
    Node
        Node producing performance metrics for the latest alpha history.
    """

    def compute(view: CacheView):
        data = view[history][history.interval]
        if not data:
            return None
        series = data[-1][1]
        return alpha_performance_node(
            series,
            risk_free_rate=risk_free_rate,
            transaction_cost=transaction_cost,
        )

    return Node(
        input=history,
        compute_fn=compute,
        name=name or f"{history.name}_performance",
        interval=history.interval,
        period=1,
    )


class AlphaPerformanceNode(Node):
    """Node wrapper computing performance metrics from alpha history."""

    def __init__(
        self,
        history: Node,
        *,
        risk_free_rate: float = 0.0,
        transaction_cost: float = 0.0,
        name: str | None = None,
    ) -> None:
        self.history = history
        self.risk_free_rate = risk_free_rate
        self.transaction_cost = transaction_cost
        super().__init__(
            input=history,
            compute_fn=self._compute,
            name=name or f"{history.name}_performance",
            interval=history.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.history][self.history.interval]
        if not data:
            return None
        series = data[-1][1]
        return alpha_performance_node(
            series,
            risk_free_rate=self.risk_free_rate,
            transaction_cost=self.transaction_cost,
        )
