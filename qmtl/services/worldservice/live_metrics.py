"""Lightweight helpers to aggregate realized/live metrics for validation."""

from __future__ import annotations

from typing import Iterable, Sequence


def _sharpe_ratio(returns: Sequence[float]) -> float | None:
    if not returns:
        return None
    avg = sum(returns) / len(returns)
    var = sum((r - avg) ** 2 for r in returns) / len(returns)
    if var == 0:
        return None
    return avg / (var ** 0.5)


def _max_drawdown(returns: Sequence[float]) -> float | None:
    if not returns:
        return None
    equity = []
    total = 0.0
    for r in returns:
        total += r
        equity.append(total)
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        drawdown = peak - v
        if drawdown > mdd:
            mdd = drawdown
    return mdd if equity else None


def aggregate_live_metrics(
    returns: Sequence[float],
    *,
    windows: Iterable[int] = (30, 60, 90),
    backtest_sharpe: float | None = None,
) -> dict[str, float | None]:
    """Aggregate realized/live metrics over sliding windows."""

    result: dict[str, float | None] = {}
    window_list = [int(w) for w in windows]
    n = len(returns)
    for window in window_list:
        if window <= 0 or n == 0:
            result[f"live_sharpe_p{window}"] = None
            result[f"live_max_drawdown_p{window}"] = None
            continue
        tail = returns[-window:] if window < n else returns
        sharpe = _sharpe_ratio(tail)
        dd = _max_drawdown(tail)
        result[f"live_sharpe_p{window}"] = sharpe
        result[f"live_max_drawdown_p{window}"] = dd

    # Canonical aliases: default to the shortest window (usually 30d)
    if window_list:
        canonical = min(window_list)
        sharpe_key = f"live_sharpe_p{canonical}"
        dd_key = f"live_max_drawdown_p{canonical}"
        if sharpe_key in result:
            result.setdefault("live_sharpe", result.get(sharpe_key))
            result.setdefault("realized_sharpe", result.get(sharpe_key))
        if dd_key in result:
            result.setdefault("live_max_drawdown", result.get(dd_key))
            result.setdefault("realized_max_drawdown", result.get(dd_key))

    if backtest_sharpe not in (None, 0) and result.get("live_sharpe") not in (None, 0):
        result.setdefault(
            "live_vs_backtest_sharpe_ratio",
            result["live_sharpe"] / backtest_sharpe,  # type: ignore[operator]
        )
    return result


def sharpe_ratio(returns: Sequence[float]) -> float | None:
    """Public helper to compute a simple Sharpe-style ratio (mean / std)."""

    return _sharpe_ratio(list(returns))


def max_drawdown_from_returns(returns: Sequence[float]) -> float | None:
    """Public helper to compute max drawdown from a return series."""

    return _max_drawdown(list(returns))


__all__ = ["aggregate_live_metrics", "max_drawdown_from_returns", "sharpe_ratio"]
