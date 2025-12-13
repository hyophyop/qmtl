"""Reusable helpers for deriving validation metrics before persistence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
import statistics
from datetime import datetime, timezone
from typing import Any, Dict

from .live_metrics import aggregate_live_metrics
from .stress_metrics import normalize_stress_metrics


def _coerce_returns(source: Any) -> list[float] | None:
    if isinstance(source, (list, tuple)):
        try:
            return [float(v) for v in source]
        except Exception:
            return None
    return None


def _finite_floats(raw: Iterable[float] | None) -> list[float]:
    if raw is None:
        return []
    clean: list[float] = []
    for value in raw:
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(candidate):
            continue
        clean.append(candidate)
    return clean


def _quantile(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    if p <= 0.0:
        return sorted_values[0]
    if p >= 1.0:
        return sorted_values[-1]
    idx = (len(sorted_values) - 1) * p
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_values[lo]
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _var_es_p01(returns: list[float]) -> tuple[float | None, float | None]:
    if len(returns) < 2:
        return None, None
    ordered = sorted(returns)
    q01 = _quantile(ordered, 0.01)
    if q01 is None:
        return None, None
    var = -q01 if q01 < 0 else 0.0
    tail = [r for r in returns if r <= q01]
    if not tail:
        return (var if math.isfinite(var) else None), None
    es_raw = statistics.fmean(tail)
    es = -es_raw if es_raw < 0 else 0.0
    if not math.isfinite(var):
        var = None
    if not math.isfinite(es):
        es = None
    return var, es


def _max_time_under_water_days(returns: list[float]) -> int | None:
    if not returns:
        return None
    equity = 0.0
    peak = 0.0
    current = 0
    longest = 0
    for r in returns:
        equity += r
        if equity < peak:
            current += 1
            longest = max(longest, current)
        else:
            peak = equity
            current = 0
    return int(longest)


def _rolling_volatility(returns: list[float], window: int) -> list[float]:
    if not returns:
        return []
    window = max(2, int(window))
    vols: list[float] = []
    for idx in range(len(returns)):
        start = max(0, idx - window + 1)
        sample = returns[start : idx + 1]
        if len(sample) < 2:
            vols.append(0.0)
            continue
        try:
            vol = statistics.pstdev(sample)
        except Exception:
            vol = 0.0
        vols.append(float(vol))
    return vols


def _regime_coverage(returns: list[float], *, window: int = 20) -> Dict[str, float] | None:
    if len(returns) < 2:
        return None
    vols = _rolling_volatility(returns, window)
    if not vols:
        return None
    ordered = sorted(vols)
    q33 = _quantile(ordered, 1.0 / 3.0)
    q66 = _quantile(ordered, 2.0 / 3.0)
    if q33 is None or q66 is None:
        return None
    low = mid = high = 0
    for vol in vols:
        if vol <= q33:
            low += 1
        elif vol > q66:
            high += 1
        else:
            mid += 1
    total = float(len(vols))
    if total <= 0:
        return None
    return {
        "low_vol": low / total,
        "mid_vol": mid / total,
        "high_vol": high / total,
    }


def _moment_stats(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    mu = statistics.fmean(values)
    diffs = [v - mu for v in values]
    m2 = statistics.fmean([d * d for d in diffs])
    if m2 <= 0:
        return None
    sigma = math.sqrt(m2)
    m3 = statistics.fmean([d**3 for d in diffs])
    m4 = statistics.fmean([d**4 for d in diffs])
    skew = m3 / (sigma**3)
    kurt = m4 / (sigma**4)
    if not (math.isfinite(skew) and math.isfinite(kurt)):
        return None
    return skew, kurt


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _simple_sharpe(returns: list[float], *, periods_per_year: int = 252) -> float | None:
    if len(returns) < 2:
        return None
    try:
        mu = statistics.fmean(returns)
        sigma = statistics.pstdev(returns)
    except Exception:
        return None
    if sigma <= 0:
        return None
    sharpe = (mu / sigma) * math.sqrt(float(periods_per_year))
    if not math.isfinite(sharpe):
        return None
    return sharpe


def _probabilistic_sharpe_ratio(
    returns: list[float],
    *,
    sharpe: float,
    benchmark_sharpe: float = 0.0,
) -> float | None:
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
    z = (sharpe - float(benchmark_sharpe)) / sigma_sr
    prob = _norm_cdf(z)
    if not math.isfinite(prob):
        return None
    return min(1.0, max(0.0, float(prob)))


def _cv_sharpe_metrics(
    returns: list[float],
    *,
    periods_per_year: int = 252,
    max_folds: int = 5,
    min_fold_size: int = 30,
) -> tuple[int | None, float | None, float | None]:
    n = len(returns)
    if n < min_fold_size * 2:
        return None, None, None
    folds_target = min(int(max_folds), n // int(min_fold_size))
    if folds_target < 2:
        return None, None, None
    fold_size = n // folds_target
    if fold_size < min_fold_size:
        return None, None, None

    sharpe_values: list[float] = []
    for i in range(folds_target):
        start = i * fold_size
        end = n if i == folds_target - 1 else (i + 1) * fold_size
        fold = returns[start:end]
        if len(fold) < 2:
            continue
        sr = _simple_sharpe(fold, periods_per_year=periods_per_year)
        if sr is not None:
            sharpe_values.append(sr)

    if len(sharpe_values) < 2:
        return None, None, None

    mean = statistics.fmean(sharpe_values)
    try:
        std = statistics.pstdev(sharpe_values)
    except Exception:
        std = 0.0
    if not math.isfinite(mean):
        mean = None
    if not math.isfinite(std):
        std = None
    return len(sharpe_values), mean, std


def _strategy_complexity(
    diagnostics: Mapping[str, Any],
) -> float | None:
    if not diagnostics:
        return None
    score = 1.0
    search_intensity = diagnostics.get("search_intensity")
    if isinstance(search_intensity, (int, float)) and not isinstance(search_intensity, bool):
        if search_intensity >= 0:
            score += math.log1p(float(search_intensity))

    extra = diagnostics.get("extra_metrics")
    if isinstance(extra, Mapping):
        for key, weight in (
            ("n_features", 0.2),
            ("feature_dim", 0.2),
            ("n_parameters", 0.2),
            ("code_cc", 0.1),
            ("nodes", 0.1),
        ):
            value = extra.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                score += weight * math.log1p(float(value))

    return float(score) if math.isfinite(score) else None


def augment_advanced_metrics(
    metrics: Mapping[str, Any] | None,
    *,
    returns: Iterable[float] | None = None,
    periods_per_year: int = 252,
) -> dict[str, Any]:
    """Derive advanced validation metrics (tail/regime/CV/complexity) from return series."""

    base: dict[str, Any] = dict(metrics or {})
    structured_keys = {"returns", "sample", "risk", "robustness", "diagnostics"}
    if not (structured_keys & set(base.keys())):
        base = {"returns": dict(base)}

    clean_returns = _finite_floats(returns)
    returns_block = base.get("returns")
    returns_map = dict(returns_block) if isinstance(returns_block, Mapping) else {}
    sample_block = base.get("sample")
    sample_map = dict(sample_block) if isinstance(sample_block, Mapping) else {}
    robustness_block = base.get("robustness")
    robustness_map = dict(robustness_block) if isinstance(robustness_block, Mapping) else {}
    diagnostics_block = base.get("diagnostics")
    diagnostics_map = dict(diagnostics_block) if isinstance(diagnostics_block, Mapping) else {}

    if clean_returns:
        if returns_map.get("var_p01") is None or returns_map.get("es_p01") is None:
            var_p01, es_p01 = _var_es_p01(clean_returns)
            returns_map.setdefault("var_p01", var_p01)
            returns_map.setdefault("es_p01", es_p01)
        if returns_map.get("max_time_under_water_days") is None:
            returns_map["max_time_under_water_days"] = _max_time_under_water_days(clean_returns)

        if sample_map.get("regime_coverage") is None:
            sample_map["regime_coverage"] = _regime_coverage(clean_returns)

        sharpe = returns_map.get("sharpe")
        sharpe_value: float | None = None
        if isinstance(sharpe, (int, float)) and not isinstance(sharpe, bool):
            sharpe_value = float(sharpe) if math.isfinite(float(sharpe)) else None
        if sharpe_value is None:
            sharpe_value = _simple_sharpe(clean_returns, periods_per_year=periods_per_year)

        if robustness_map.get("probabilistic_sharpe_ratio") is None and sharpe_value is not None:
            robustness_map["probabilistic_sharpe_ratio"] = _probabilistic_sharpe_ratio(
                clean_returns,
                sharpe=sharpe_value,
                benchmark_sharpe=0.0,
            )

        if (
            robustness_map.get("cv_folds") is None
            or robustness_map.get("cv_sharpe_mean") is None
            or robustness_map.get("cv_sharpe_std") is None
        ):
            folds, mean, std = _cv_sharpe_metrics(clean_returns, periods_per_year=periods_per_year)
            robustness_map.setdefault("cv_folds", folds)
            robustness_map.setdefault("cv_sharpe_mean", mean)
            robustness_map.setdefault("cv_sharpe_std", std)

    if diagnostics_map.get("strategy_complexity") is None:
        diagnostics_map["strategy_complexity"] = _strategy_complexity(diagnostics_map)

    if returns_map:
        base["returns"] = returns_map
    if sample_map:
        base["sample"] = sample_map
    if robustness_map:
        base["robustness"] = robustness_map
    if diagnostics_map:
        base["diagnostics"] = diagnostics_map

    return base


def augment_live_metrics(
    metrics: Mapping[str, Any] | None, *, windows: Iterable[int] = (30, 60, 90)
) -> dict[str, Any]:
    """Attach live monitoring aggregates if realized returns are present."""

    if not metrics:
        return {}
    diagnostics = dict(metrics.get("diagnostics") or {})
    live_returns = _coerce_returns(diagnostics.get("live_returns"))
    if live_returns is None:
        live_returns = _coerce_returns(metrics.get("live_returns"))
    if live_returns is None:
        live = metrics.get("live")
        if isinstance(live, Mapping):
            live_returns = _coerce_returns(live.get("returns"))
    if live_returns is None:
        return dict(metrics)

    backtest_sharpe: float | None = None
    returns_block = metrics.get("returns")
    if isinstance(returns_block, Mapping):
        val = returns_block.get("sharpe")
        if isinstance(val, (int, float)):
            backtest_sharpe = float(val)

    aggregates = aggregate_live_metrics(
        [float(r) for r in live_returns],
        windows=windows,
        backtest_sharpe=backtest_sharpe,
    )
    diagnostics.update(aggregates)
    diagnostics.setdefault("live_returns_len", len(live_returns))
    merged = dict(metrics)
    merged["diagnostics"] = diagnostics
    return merged


def augment_stress_metrics(
    metrics: Mapping[str, Any] | None,
    *,
    policy_payload: Any | None,
) -> dict[str, Any]:
    """Normalize stress scenario metrics and derive missing dot-path keys."""

    if not metrics:
        return {}
    base = dict(metrics)
    policy = policy_payload
    scenarios = None
    if isinstance(policy_payload, Mapping) and "policy" in policy_payload:
        policy = policy_payload.get("policy")
    if isinstance(policy, Mapping):
        stress = policy.get("stress")
        if isinstance(stress, Mapping):
            scenarios = stress.get("scenarios")
    flat = normalize_stress_metrics(
        base,
        scenarios=scenarios if isinstance(scenarios, Mapping) else None,
    )
    if flat:
        stress_section = base.get("stress")
        stress_section = dict(stress_section) if isinstance(stress_section, Mapping) else {}
        for key, value in flat.items():
            parts = key.split(".")
            if len(parts) != 3 or parts[0] != "stress":
                continue
            scenario, field = parts[1], parts[2]
            bucket = stress_section.setdefault(scenario, {})
            if isinstance(bucket, dict):
                bucket.setdefault(field, value)
        base["stress"] = stress_section
    return base


def augment_portfolio_metrics(
    metrics: Mapping[str, Any] | None,
    *,
    baseline_sharpe: float | None = None,
    baseline_var_99: float | None = None,
    baseline_es_99: float | None = None,
) -> dict[str, Any]:
    """Derive portfolio-oriented metrics (incremental risk, sharpe uplift).

    - If missing, set risk.incremental_var_99 / incremental_es_99 using max_drawdown proxy.
    - Compute diagnostics.extra_metrics.portfolio_sharpe_uplift using baseline or benchmark sharpe.
    """

    if not metrics:
        return {}

    base = dict(metrics)
    returns = base.get("returns") if isinstance(base.get("returns"), Mapping) else {}
    risk = dict(base.get("risk") or {})
    diagnostics = dict(base.get("diagnostics") or {})
    extra = dict(diagnostics.get("extra_metrics") or {})

    returns_sharpe = returns.get("sharpe") if isinstance(returns, Mapping) else None
    max_dd = returns.get("max_drawdown") if isinstance(returns, Mapping) else None

    # Baseline markers for uplift/aggregate reporting
    if baseline_sharpe is not None:
        extra.setdefault("portfolio_baseline_sharpe", baseline_sharpe)
    if baseline_var_99 is not None:
        extra.setdefault("portfolio_baseline_var_99", baseline_var_99)
    if baseline_es_99 is not None:
        extra.setdefault("portfolio_baseline_es_99", baseline_es_99)

    benchmark = extra.get("portfolio_baseline_sharpe") or extra.get("benchmark_sharpe")
    baseline = baseline_sharpe if baseline_sharpe is not None else benchmark if isinstance(benchmark, (int, float)) else None

    candidate_var = risk.get("incremental_var_99")
    if candidate_var is None and baseline_var_99 is not None:
        candidate_var = float(baseline_var_99)
        risk["incremental_var_99"] = candidate_var

    if candidate_var is None and isinstance(max_dd, (int, float)):
        candidate_var = abs(float(max_dd))
        risk["incremental_var_99"] = candidate_var

    candidate_es = risk.get("incremental_es_99")
    if candidate_es is None and baseline_es_99 is not None:
        candidate_es = float(baseline_es_99)
        risk["incremental_es_99"] = candidate_es
    if candidate_es is None and candidate_var is not None:
        candidate_es = abs(float(candidate_var)) * 1.2
        risk.setdefault("incremental_es_99", candidate_es)

    if "portfolio_sharpe_uplift" not in extra and isinstance(returns_sharpe, (int, float)):
        extra["portfolio_sharpe_uplift"] = float(returns_sharpe) - float(baseline or 0.0)

    if candidate_var is not None:
        extra.setdefault("portfolio_var_99_with_candidate", float(baseline_var_99 or 0.0) + float(candidate_var))
    if candidate_es is not None:
        extra.setdefault("portfolio_es_99_with_candidate", float(baseline_es_99 or 0.0) + float(candidate_es))

    diagnostics["extra_metrics"] = extra
    base["risk"] = risk
    base["diagnostics"] = diagnostics
    return base


def iso_timestamp_now() -> str:
    """Return a UTC timestamp string without fractional seconds."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


__all__ = [
    "augment_advanced_metrics",
    "augment_live_metrics",
    "augment_stress_metrics",
    "augment_portfolio_metrics",
    "iso_timestamp_now",
]
