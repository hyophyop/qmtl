from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from qmtl.runtime.transforms.alpha_performance import alpha_performance_node

DEFAULT_PERIODS_PER_YEAR = 252
_EULER_MASCHERONI = 0.5772156649015329


def _finite_returns(raw: Sequence[float | None]) -> list[float]:
    clean: list[float] = []
    for value in raw:
        if value is None:
            continue
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(candidate):
            continue
        clean.append(candidate)
    return clean


def _alpha_metric(raw: Mapping[str, Any], name: str) -> float | None:
    for key in (name, f"alpha_performance.{name}"):
        value = raw.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            candidate = float(value)
            if math.isfinite(candidate):
                return candidate
    return None


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        candidate = float(value)
        return candidate if math.isfinite(candidate) else None
    return None


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float | None:
    """Inverse standard-normal CDF (Acklam approximation)."""

    if not (0.0 < p < 1.0):
        return None

    a1 = -39.69683028665376
    a2 = 220.9460984245205
    a3 = -275.9285104469687
    a4 = 138.3577518672690
    a5 = -30.66479806614716
    a6 = 2.506628277459239

    b1 = -54.47609879822406
    b2 = 161.5858368580409
    b3 = -155.6989798598866
    b4 = 66.80131188771972
    b5 = -13.28068155288572

    c1 = -0.007784894002430293
    c2 = -0.3223964580411365
    c3 = -2.400758277161838
    c4 = -2.549732539343734
    c5 = 4.374664141464968
    c6 = 2.938163982698783

    d1 = 0.007784695709041462
    d2 = 0.3224671290700398
    d3 = 2.445134137142996
    d4 = 3.754408661907416

    plow = 0.02425
    phigh = 1.0 - plow

    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        num = (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6)
        den = ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
        return -(num / den)

    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        num = (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6)
        den = ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
        return num / den

    q = p - 0.5
    r = q * q
    num = (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6) * q
    den = (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1.0)
    return num / den


def gain_to_pain_ratio(returns: Sequence[float]) -> float | None:
    """Compute Gain-to-Pain ratio.

    Uses the common definition: total return divided by the absolute sum of losses.
    """

    if not returns:
        return None
    losses = sum(r for r in returns if r < 0)
    denom = abs(losses)
    if denom <= 0:
        return None
    total = sum(returns)
    ratio = total / denom
    return ratio if math.isfinite(ratio) else None


def time_under_water_ratio(returns: Sequence[float]) -> float | None:
    """Fraction of periods spent below the equity peak."""

    if not returns:
        return None
    equity = 0.0
    peak = 0.0
    underwater = 0
    for r in returns:
        equity += r
        peak = max(peak, equity)
        if equity < peak:
            underwater += 1
    ratio = underwater / len(returns)
    return ratio if math.isfinite(ratio) else None


def _effective_history_years(n_periods: int, *, periods_per_year: int) -> float | None:
    if n_periods <= 0 or periods_per_year <= 0:
        return None
    years = n_periods / float(periods_per_year)
    return years if math.isfinite(years) else None


def _moment_stats(values: Sequence[float]) -> tuple[float, float] | None:
    """Return (skewness, kurtosis) using population moments."""

    if len(values) < 2:
        return None
    mu = _mean(values)
    diffs = [v - mu for v in values]
    m2 = _mean([d * d for d in diffs])
    if m2 <= 0:
        return None
    sigma = math.sqrt(m2)
    m3 = _mean([d**3 for d in diffs])
    m4 = _mean([d**4 for d in diffs])
    skew = m3 / (sigma**3)
    kurt = m4 / (sigma**4)
    if not (math.isfinite(skew) and math.isfinite(kurt)):
        return None
    return skew, kurt


def deflated_sharpe_ratio(
    returns: Sequence[float],
    *,
    sharpe: float,
    trials: int = 1,
) -> float | None:
    """Compute a deflated Sharpe ratio as a probability in [0, 1]."""

    if len(returns) < 2:
        return None
    if not math.isfinite(sharpe):
        return None

    stats = _moment_stats(returns)
    if stats is None:
        return None
    skew, kurt = stats

    denom = len(returns) - 1
    if denom <= 0:
        return None

    numerator = 1.0 - skew * sharpe + ((kurt - 1.0) / 4.0) * (sharpe**2)
    if numerator <= 0.0:
        return None

    sigma_sr = math.sqrt(numerator / denom)
    if sigma_sr <= 0.0 or not math.isfinite(sigma_sr):
        return None

    threshold = 0.0
    trials = int(trials)
    if trials > 1:
        p1 = 1.0 - (1.0 / trials)
        p2 = 1.0 - (1.0 / (trials * math.e))
        z1 = _norm_ppf(p1)
        z2 = _norm_ppf(p2)
        if z1 is not None and z2 is not None:
            threshold = sigma_sr * ((1.0 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)

    prob = _norm_cdf((sharpe - threshold) / sigma_sr)
    if not math.isfinite(prob):
        return None
    return min(1.0, max(0.0, prob))


def _split_halves(values: Sequence[float]) -> tuple[list[float], list[float]]:
    if not values:
        return [], []
    mid = len(values) // 2
    if mid <= 0:
        return [], list(values)
    return list(values[:mid]), list(values[mid:])


def _sharpe_from_returns(
    returns: Sequence[float],
    *,
    risk_free_rate: float,
    transaction_cost: float,
) -> float | None:
    raw = alpha_performance_node(
        returns,
        risk_free_rate=risk_free_rate,
        transaction_cost=transaction_cost,
    )
    return _alpha_metric(raw, "sharpe")


def build_v1_evaluation_metrics(
    returns: Sequence[float],
    *,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    risk_free_rate: float = 0.0,
    transaction_cost: float = 0.0,
    search_intensity: int = 1,
    returns_source: str | None = None,
    risk_metrics: Mapping[str, Any] | None = None,
    extra_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an EvaluationMetrics-like payload for WorldService v1 core checks."""

    clean_returns = _finite_returns(returns)
    perf = alpha_performance_node(
        clean_returns,
        risk_free_rate=risk_free_rate,
        transaction_cost=transaction_cost,
    )

    sharpe = _alpha_metric(perf, "sharpe")
    max_dd = _alpha_metric(perf, "max_drawdown")
    max_dd_abs = abs(max_dd) if max_dd is not None else None

    gpr = gain_to_pain_ratio(clean_returns)
    tuw = time_under_water_ratio(clean_returns)

    n_periods = len(clean_returns)
    eff_years = _effective_history_years(n_periods, periods_per_year=periods_per_year)
    trades_total: int | None = n_periods if n_periods else None
    trades_per_year = (n_periods / eff_years) if eff_years else None
    if trades_per_year is not None and not math.isfinite(trades_per_year):
        trades_per_year = None

    first, second = _split_halves(clean_returns)
    sharpe_first = _sharpe_from_returns(
        first,
        risk_free_rate=risk_free_rate,
        transaction_cost=transaction_cost,
    )
    sharpe_second = _sharpe_from_returns(
        second,
        risk_free_rate=risk_free_rate,
        transaction_cost=transaction_cost,
    )

    dsr = deflated_sharpe_ratio(
        clean_returns,
        sharpe=sharpe if sharpe is not None else 0.0,
        trials=search_intensity,
    )

    diagnostics: dict[str, Any] = {"search_intensity": int(search_intensity)}
    if returns_source is not None:
        diagnostics["returns_source"] = str(returns_source)
    if extra_metrics:
        diagnostics["extra_metrics"] = dict(extra_metrics)

    risk: dict[str, Any] = {}
    if risk_metrics:
        adv_util = _finite_float(risk_metrics.get("adv_utilization_p95"))
        participation = _finite_float(risk_metrics.get("participation_rate_p95"))
        if adv_util is not None:
            risk["adv_utilization_p95"] = adv_util
        if participation is not None:
            risk["participation_rate_p95"] = participation

    return {
        "returns": {
            "sharpe": sharpe,
            "max_drawdown": max_dd_abs,
            "gain_to_pain_ratio": gpr,
            "time_under_water_ratio": tuw,
        },
        "sample": {
            "effective_history_years": eff_years,
            "n_trades_total": trades_total,
            "n_trades_per_year": trades_per_year,
        },
        "risk": risk or None,
        "robustness": {
            "deflated_sharpe_ratio": dsr,
            "sharpe_first_half": sharpe_first,
            "sharpe_second_half": sharpe_second,
        },
        "diagnostics": diagnostics,
    }


__all__ = [
    "DEFAULT_PERIODS_PER_YEAR",
    "build_v1_evaluation_metrics",
    "deflated_sharpe_ratio",
    "gain_to_pain_ratio",
    "time_under_water_ratio",
]
