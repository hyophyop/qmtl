from __future__ import annotations

from collections.abc import Sequence
import math
from typing import Iterable

from qmtl.runtime.alpha_metrics import default_alpha_performance_metrics
from qmtl.runtime.transforms.alpha_performance import alpha_performance_node

from .schemas import AlphaMetricsEnvelope, RebalancePlanModel, StrategySeries


def _float_sequence(values: Iterable[float | None]) -> list[float]:
    result: list[float] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        result.append(float(value))
    return result


def _returns_from_equity(equity: Sequence[float]) -> list[float]:
    """Turn an equity curve into simple returns (differences normalized against prior value)."""
    clean: list[float] = []
    prev: float | None = None
    for point in equity:
        if prev is None:
            prev = float(point)
            continue
        current = float(point)
        if prev != 0.0:
            clean.append((current - prev) / prev)
        else:
            clean.append(0.0 if current == 0.0 else float("inf"))
        prev = current
    return clean


def equity_curve_to_returns(equity: Sequence[float | None]) -> list[float]:
    return _returns_from_equity(_float_sequence(equity))


def _series_to_returns(series: StrategySeries) -> list[float]:
    if series.returns:
        return _float_sequence(series.returns)
    if series.pnl:
        return _float_sequence(series.pnl)
    if series.equity:
        return equity_curve_to_returns(series.equity)
    return []


def alpha_performance_metrics_from_returns(returns: Sequence[float]) -> dict[str, float]:
    clean = [
        float(value)
        for value in returns
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    if not clean:
        return default_alpha_performance_metrics()
    raw = alpha_performance_node(clean)
    return {f"alpha_performance.{key}": float(value) for key, value in raw.items()}


def alpha_performance_metrics_from_series(series: StrategySeries) -> dict[str, float]:
    return alpha_performance_metrics_from_returns(_series_to_returns(series))


def build_alpha_metrics_envelope(per_world: dict[str, RebalancePlanModel]) -> AlphaMetricsEnvelope:
    envelope = AlphaMetricsEnvelope()
    for world_id, plan in per_world.items():
        envelope.per_world[world_id] = default_alpha_performance_metrics()
        for strategy_id in plan.scale_by_strategy.keys():
            world_map = envelope.per_strategy.setdefault(strategy_id, {})
            world_map[world_id] = default_alpha_performance_metrics()
    return envelope
