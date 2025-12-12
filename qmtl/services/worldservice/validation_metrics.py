"""Reusable helpers for deriving validation metrics before persistence."""

from __future__ import annotations

from collections.abc import Mapping
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


def augment_live_metrics(metrics: Mapping[str, Any] | None) -> dict[str, Any]:
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


__all__ = ["augment_live_metrics", "augment_stress_metrics", "augment_portfolio_metrics", "iso_timestamp_now"]
