"""Compute performance metrics from alpha series."""

import math
from collections.abc import Sequence
from typing import Optional
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.execution_modeling import ExecutionFill


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


def calculate_execution_metrics(fills: Sequence[ExecutionFill]) -> dict[str, float]:
    """Calculate aggregate execution quality metrics from fills."""
    if not fills:
        return {}

    total_commission = sum(f.commission for f in fills)
    total_slippage = sum(abs(f.slippage * f.quantity) for f in fills)
    total_market_impact = sum(f.market_impact * f.quantity for f in fills)
    total_volume = sum(f.quantity for f in fills)

    avg_commission_bps = (total_commission / total_volume) * 10000 if total_volume else 0
    avg_slippage_bps = (total_slippage / total_volume) * 10000 if total_volume else 0
    avg_market_impact_bps = (total_market_impact / total_volume) * 10000 if total_volume else 0

    total_shortfall = sum(f.execution_shortfall * f.quantity for f in fills)
    avg_shortfall_bps = (total_shortfall / total_volume) * 10000 if total_volume else 0

    return {
        "total_trades": len(fills),
        "total_volume": total_volume,
        "total_commission": total_commission,
        "total_slippage": total_slippage,
        "total_market_impact": total_market_impact,
        "avg_commission_bps": avg_commission_bps,
        "avg_slippage_bps": avg_slippage_bps,
        "avg_market_impact_bps": avg_market_impact_bps,
        "avg_execution_shortfall_bps": avg_shortfall_bps,
        "total_execution_cost": total_commission + total_slippage + total_market_impact,
    }


def adjust_returns_for_costs(raw_returns: Sequence[float], fills: Sequence[ExecutionFill]) -> list[float]:
    """Adjust returns for execution costs estimated from fills."""
    if not fills or not raw_returns:
        return list(raw_returns)

    metrics = calculate_execution_metrics(fills)
    avg_cost_per_trade = metrics.get("total_execution_cost", 0) / len(fills)
    cost_per_period = avg_cost_per_trade / len(raw_returns)

    adjusted = []
    for ret in raw_returns:
        cost_impact = cost_per_period / 10000.0
        adjusted.append(ret - cost_impact)
    return adjusted


def alpha_performance_node(
    returns: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    transaction_cost: float = 0.0,
    execution_fills: Optional[Sequence[ExecutionFill]] = None,
    use_realistic_costs: bool = False
) -> dict:
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
    dict
        Mapping containing ``sharpe``, ``max_drawdown``, ``win_ratio``,
        ``profit_factor``, ``car_mdd``, ``rar_mdd`` and execution quality metrics.
    """

    # Drop NaN values
    clean_returns = [r for r in returns if not math.isnan(r)]
    if not clean_returns:
        return {
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_ratio": 0.0,
            "profit_factor": 0.0,
            "car_mdd": 0.0,
            "rar_mdd": 0.0,
        }

    # Apply transaction costs
    if use_realistic_costs and execution_fills:
        net_returns = adjust_returns_for_costs(clean_returns, execution_fills)
        execution_metrics = calculate_execution_metrics(execution_fills)
    else:
        # Simple transaction cost model
        net_returns = [r - transaction_cost for r in clean_returns]
        execution_metrics = {}

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

    result = {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_ratio": win_ratio,
        "profit_factor": profit_factor,
        "car_mdd": car_mdd,
        "rar_mdd": rar_mdd,
    }
    
    # Add execution metrics if available
    if execution_metrics:
        result.update({
            f"execution_{k}": v for k, v in execution_metrics.items()
        })
    
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
