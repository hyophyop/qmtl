"""Compute performance metrics from alpha series."""

TAGS = {
    "scope": "transform",
    "family": "alpha_performance",
    "interval": "1d",
    "asset": "sample",
}

import math
from collections.abc import Sequence
from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def _car_mdd(returns: Sequence[float], max_drawdown: float) -> float:
    """Compute cumulative return over maximum drawdown."""
    car = math.prod(1 + r for r in returns) - 1
    return car / abs(max_drawdown) if max_drawdown else float("inf")


def _rar_mdd(
    returns: Sequence[float], max_drawdown: float, risk_free_rate: float
) -> float:
    """Compute risk-adjusted return over maximum drawdown."""
    excess = [r - risk_free_rate for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((r - mean) ** 2 for r in excess) / len(excess)
    std = math.sqrt(variance)
    rar = mean / std if std else 0.0
    return rar / abs(max_drawdown) if max_drawdown else float("inf")


def alpha_performance_node(
    returns: Sequence[float], *, risk_free_rate: float = 0.0, transaction_cost: float = 0.0
) -> dict:
    """Return key performance metrics from a return series.

    Parameters
    ----------
    returns:
        Sequence of periodic returns.
    risk_free_rate:
        Optional risk-free rate used when computing the Sharpe ratio.
    transaction_cost:
        Optional transaction cost subtracted from each return.

    Returns
    -------
    dict
        Mapping containing ``sharpe``, ``max_drawdown``, ``win_ratio``,
        ``profit_factor``, ``car_mdd`` and ``rar_mdd`` values.
    """

    if not returns:
        return {
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_ratio": 0.0,
            "profit_factor": 0.0,
            "car_mdd": 0.0,
            "rar_mdd": 0.0,
        }

    # Apply transaction cost
    net_returns = [r - transaction_cost for r in returns]

    # Sharpe ratio
    excess = [r - risk_free_rate for r in net_returns]
    mean = sum(excess) / len(excess)
    variance = sum((r - mean) ** 2 for r in excess) / len(excess)
    std = math.sqrt(variance)
    sharpe = mean / std if std else 0.0

    # Max drawdown based on cumulative returns
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in net_returns:
        equity += r
        peak = max(peak, equity)
        drawdown = equity - peak
        if drawdown < max_dd:
            max_dd = drawdown

    # Win ratio
    wins = sum(1 for r in net_returns if r > 0)
    win_ratio = wins / len(net_returns)

    # Profit factor
    gross_profit = sum(r for r in net_returns if r > 0)
    gross_loss = sum(r for r in net_returns if r < 0)
    profit_factor = gross_profit / abs(gross_loss) if gross_loss else float("inf")

    # CAR/MDD and RAR/MDD ratios
    car_mdd = _car_mdd(net_returns, max_dd)
    rar_mdd = _rar_mdd(net_returns, max_dd, risk_free_rate)

    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_ratio": win_ratio,
        "profit_factor": profit_factor,
        "car_mdd": car_mdd,
        "rar_mdd": rar_mdd,
    }


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
