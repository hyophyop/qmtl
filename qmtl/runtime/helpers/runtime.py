"""Runtime helper utilities shared across gateway and SDK modules."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Sequence

from qmtl.foundation.common.compute_key import DEFAULT_EXECUTION_DOMAIN
from qmtl.runtime.alpha_metrics import alpha_metric_key, default_alpha_performance_metrics
from qmtl.runtime.sdk.execution_modeling import ExecutionFill

_CANONICAL_MODES = {"backtest", "dryrun", "live", "shadow"}
_MODE_ALIASES = {
    "backtest": "backtest",
    "backtesting": "backtest",
    "dryrun": "dryrun",
    "dry-run": "dryrun",
    "dry_run": "dryrun",
    "paper": "dryrun",
    "live": "live",
    "prod": "live",
    "production": "live",
    "shadow": "shadow",
}
_DEPRECATED_MODES = {
    "compute-only",
    "computeonly",
    "compute_only",
    "compute",
    "offline",
    "sandbox",
    "sim",
    "simulation",
    "validate",
    "validation",
    "default",
}
_CLOCKS = {"virtual", "wall"}


@dataclass(frozen=True)
class ExecutionContextResolution:
    """Result of resolving an execution context."""

    context: dict[str, str]
    force_offline: bool
    downgraded: bool = False
    downgrade_reason: str | None = None
    safe_mode: bool = False


@dataclass(frozen=True)
class ActivationMetadata:
    """Metadata extracted from activation events."""

    version: int | None
    etag: str | None
    run_id: str | None
    ts: str | None
    state_hash: str | None
    effective_mode: str | None


@dataclass(frozen=True)
class ActivationUpdate:
    """Normalized activation payload used by clients."""

    side: str | None
    active: bool | None
    freeze: bool | None
    drain: bool | None
    weight: float | None
    metadata: ActivationMetadata


# ---------------------------------------------------------------------------
# Execution context helpers
# ---------------------------------------------------------------------------


def _normalize_mode_token(value: str, *, field: str) -> str:
    """Normalize execution mode/domain tokens with strict validation.

    Accepted: backtest, dryrun/paper, live, shadow (plus minimal aliases).
    Deprecated/legacy tokens raise with guidance instead of silently downgrading.
    """

    token = value.strip().lower()
    if not token:
        raise ValueError(f"{field} must be provided")

    if token in _DEPRECATED_MODES:
        raise ValueError(
            f"{field} '{value}' is deprecated; use one of backtest, paper, live, or shadow"
        )

    normalized = _MODE_ALIASES.get(token, token)
    if normalized in _CANONICAL_MODES:
        return normalized

    raise ValueError(
        f"{field} '{value}' is not supported; choose from backtest, paper, live, or shadow"
    )


def _mode_from_domain(domain: str | None, *, field: str = "execution_domain") -> str | None:
    if domain is None:
        return None
    token = str(domain).strip()
    if not token or token.lower() == DEFAULT_EXECUTION_DOMAIN:
        return None
    return _normalize_mode_token(token, field=field)


def _normalize_mode(value: str | None) -> str:
    if value is None:
        raise ValueError("execution_mode must be provided")
    return _normalize_mode_token(value, field="execution_mode")


def _validate_clock(value: object, *, expected: str, mode: str | None = None) -> str:
    cval = str(value).strip().lower()
    if cval not in _CLOCKS:
        raise ValueError("clock must be one of 'virtual' or 'wall'")
    if cval != expected:
        if mode:
            raise ValueError(f"{mode} runs require '{expected}' clock but received '{value}'")
        raise ValueError(f"runs require '{expected}' clock but received '{value}'")
    return cval


def determine_execution_mode(
    *,
    explicit_mode: str | None,
    execution_domain: str | None,
    merged_context: Mapping[str, str],
    trade_mode: str,
    offline_requested: bool,
    gateway_url: str | None,
) -> str:
    """Determine the execution mode from user inputs and existing context.

    execution_domain hints are intentionally ignored; callers must pass
    explicit_mode (or set execution_mode in context) to steer behaviour.
    """

    if explicit_mode is not None:
        return _normalize_mode(explicit_mode)

    existing = merged_context.get("execution_mode")
    if existing:
        return _normalize_mode(existing)

    if trade_mode == "live" and not offline_requested:
        return "live"
    if gateway_url and not offline_requested:
        return "live"
    return "backtest"


def normalize_clock_value(
    merged: MutableMapping[str, str],
    *,
    clock: str | None,
    mode: str,
) -> None:
    """Normalize the clock entry for an execution context."""

    expected_clock = "wall" if mode in {"live", "shadow"} else "virtual"
    if clock is not None:
        merged["clock"] = _validate_clock(clock, expected=expected_clock, mode=mode)
        return

    existing = merged.get("clock")
    if existing is not None:
        merged["clock"] = _validate_clock(existing, expected=expected_clock, mode=mode)
        return

    merged["clock"] = expected_clock


def _apply_optional_field(
    merged: MutableMapping[str, str],
    key: str,
    value: object | None,
) -> None:
    if value is not None:
        text = str(value).strip()
        if text:
            merged[key] = text
        else:
            merged.pop(key, None)
        return

    if key not in merged:
        return

    text = str(merged[key]).strip()
    if text:
        merged[key] = text
    else:
        merged.pop(key, None)


def apply_temporal_requirements(
    merged: MutableMapping[str, str],
    *,
    mode: str,
    as_of: object | None,
    dataset_fingerprint: str | None,
    gateway_url: str | None,
    offline_requested: bool,
) -> bool:
    """Normalize temporal fields and return whether we must force offline mode."""

    _apply_optional_field(merged, "as_of", as_of)
    _apply_optional_field(merged, "dataset_fingerprint", dataset_fingerprint)

    if mode in {"live", "shadow"}:
        merged.pop("as_of", None)
        merged.pop("dataset_fingerprint", None)
        return False

    has_as_of = bool(merged.get("as_of"))
    has_dataset = bool(merged.get("dataset_fingerprint"))
    if has_as_of and has_dataset:
        return False

    force_offline = bool(gateway_url and not offline_requested)
    merged.pop("as_of", None)
    merged.pop("dataset_fingerprint", None)
    return force_offline


# ---------------------------------------------------------------------------
# Activation helpers
# ---------------------------------------------------------------------------


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_weight(weight: float | None, *, active: bool | None) -> float | None:
    """Clamp activation weights to [0, 1] with sensible defaults."""

    if weight is None:
        if active is None:
            return None
        return 1.0 if active else 0.0
    if weight < 0.0:
        return 0.0
    if weight > 1.0:
        return 1.0
    return weight


def parse_activation_update(payload: Mapping[str, Any]) -> ActivationUpdate:
    """Return a normalized representation of an activation payload."""

    side_raw = payload.get("side")
    side = _clean_str(side_raw)
    if side is not None:
        side = side.lower()

    active = payload.get("active")
    active_bool = bool(active) if active is not None else None

    weight_raw = payload.get("weight")
    weight_value: float | None
    invalid_weight = False
    if weight_raw is None:
        weight_value = None
    else:
        try:
            weight_value = float(weight_raw)
        except (TypeError, ValueError):
            weight_value = None
            invalid_weight = True

    metadata = ActivationMetadata(
        version=_coerce_optional_int(payload.get("version")),
        etag=_clean_str(payload.get("etag")),
        run_id=_clean_str(payload.get("run_id")),
        ts=_clean_str(payload.get("ts")),
        state_hash=_clean_str(payload.get("state_hash")),
        effective_mode=_clean_str(payload.get("effective_mode")),
    )

    return ActivationUpdate(
        side=side,
        active=active_bool,
        freeze=_coerce_optional_bool(payload.get("freeze")),
        drain=_coerce_optional_bool(payload.get("drain")),
        weight=(
            normalize_weight(weight_value, active=active_bool)
            if not invalid_weight
            else None
        ),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Alpha performance helpers
# ---------------------------------------------------------------------------


def _car_mdd(returns: Sequence[float], max_drawdown: float) -> float:
    car = math.prod(1 + r for r in returns) - 1
    return car / abs(max_drawdown) if max_drawdown else float("inf")


def _rar_mdd(
    returns: Sequence[float], max_drawdown: float, risk_free_rate: float
) -> float:
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

    if total_volume:
        avg_commission_bps = (total_commission / total_volume) * 10000
        avg_slippage_bps = (total_slippage / total_volume) * 10000
        avg_market_impact_bps = (total_market_impact / total_volume) * 10000
        avg_shortfall_bps = (
            sum(f.execution_shortfall * f.quantity for f in fills) / total_volume
        ) * 10000
    else:
        avg_commission_bps = 0.0
        avg_slippage_bps = 0.0
        avg_market_impact_bps = 0.0
        avg_shortfall_bps = 0.0

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


def _execution_cost_per_period(metrics: Mapping[str, float], periods: int) -> float:
    if not periods:
        return 0.0
    total_cost = metrics.get("total_execution_cost", 0.0)
    trades = metrics.get("total_trades", 0.0)
    if not trades:
        return 0.0
    return (total_cost / trades) / periods


def adjust_returns_for_costs(
    raw_returns: Sequence[float], fills: Sequence[ExecutionFill]
) -> list[float]:
    """Adjust returns for execution costs estimated from fills."""

    if not fills or not raw_returns:
        return list(raw_returns)

    metrics = calculate_execution_metrics(fills)
    cost_per_period = _execution_cost_per_period(metrics, len(raw_returns)) / 10000.0
    return [ret - cost_per_period for ret in raw_returns]


def _max_drawdown(returns: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in returns:
        equity += r
        peak = max(peak, equity)
        drawdown = equity - peak
        if drawdown < max_dd:
            max_dd = drawdown
    return max_dd


def _win_ratio(returns: Sequence[float]) -> float:
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns)


def _profit_factor(returns: Sequence[float]) -> float:
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = sum(r for r in returns if r < 0)
    return gross_profit / abs(gross_loss) if gross_loss else float("inf")


def _clean_returns(returns: Sequence[float]) -> list[float]:
    return [float(r) for r in returns if not math.isnan(r)]


def _net_returns_and_execution_metrics(
    clean_returns: Sequence[float],
    *,
    transaction_cost: float,
    execution_fills: Sequence[ExecutionFill] | None,
    use_realistic_costs: bool,
) -> tuple[list[float], dict[str, float]]:
    if use_realistic_costs and execution_fills:
        net_returns = adjust_returns_for_costs(clean_returns, execution_fills)
        execution_metrics = calculate_execution_metrics(execution_fills)
    else:
        net_returns = [r - transaction_cost for r in clean_returns]
        execution_metrics: dict[str, float] = {}
    return net_returns, execution_metrics


def _excess_returns(net_returns: Sequence[float], risk_free_rate: float) -> list[float]:
    return [r - risk_free_rate for r in net_returns]


def _sharpe_ratio(excess_returns: Sequence[float]) -> float:
    if not excess_returns:
        return 0.0
    mean = sum(excess_returns) / len(excess_returns)
    variance = sum((r - mean) ** 2 for r in excess_returns) / len(excess_returns)
    std = math.sqrt(variance)
    return mean / std if std else 0.0


def _alpha_core_metrics(
    net_returns: Sequence[float],
    *,
    risk_free_rate: float,
) -> dict[str, float]:
    excess = _excess_returns(net_returns, risk_free_rate)
    sharpe = _sharpe_ratio(excess)
    max_dd = _max_drawdown(net_returns)
    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_ratio": _win_ratio(net_returns),
        "profit_factor": _profit_factor(net_returns),
        "car_mdd": _car_mdd(net_returns, max_dd),
        "rar_mdd": _rar_mdd(net_returns, max_dd, risk_free_rate),
    }


def compute_alpha_performance_summary(
    returns: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    transaction_cost: float = 0.0,
    execution_fills: Sequence[ExecutionFill] | None = None,
    use_realistic_costs: bool = False,
) -> dict[str, float]:
    """Return a mapping with alpha-performance metrics and execution costs."""

    clean_returns = _clean_returns(returns)
    if not clean_returns:
        return default_alpha_performance_metrics()

    net_returns, execution_metrics = _net_returns_and_execution_metrics(
        clean_returns,
        transaction_cost=transaction_cost,
        execution_fills=execution_fills,
        use_realistic_costs=use_realistic_costs,
    )
    metrics = _alpha_core_metrics(net_returns, risk_free_rate=risk_free_rate)

    result = {alpha_metric_key(name): value for name, value in metrics.items()}
    if execution_metrics:
        result.update({f"execution_{k}": v for k, v in execution_metrics.items()})
    return result


__all__ = [
    "ActivationMetadata",
    "ActivationUpdate",
    "ExecutionContextResolution",
    "adjust_returns_for_costs",
    "apply_temporal_requirements",
    "calculate_execution_metrics",
    "compute_alpha_performance_summary",
    "determine_execution_mode",
    "normalize_clock_value",
    "normalize_weight",
    "parse_activation_update",
]
