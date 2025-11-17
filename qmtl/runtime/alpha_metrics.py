from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict, Tuple

ALPHA_PERFORMANCE_METRIC_PREFIX = "alpha_performance."
ALPHA_PERFORMANCE_METRIC_KEYS: Tuple[str, ...] = (
    "sharpe",
    "max_drawdown",
    "win_ratio",
    "profit_factor",
    "car_mdd",
    "rar_mdd",
)


def alpha_metric_key(metric: str) -> str:
    """Return the fully qualified key for a given metric (with prefix)."""

    return f"{ALPHA_PERFORMANCE_METRIC_PREFIX}{metric}"


def default_alpha_performance_metrics() -> dict[str, float]:
    """Return a fresh mapping that defaults every alpha metric to 0.0."""

    return {alpha_metric_key(key): 0.0 for key in ALPHA_PERFORMANCE_METRIC_KEYS}


def _is_alpha_performance_key(key: str) -> str | None:
    if not key.startswith(ALPHA_PERFORMANCE_METRIC_PREFIX):
        return None
    candidate = key[len(ALPHA_PERFORMANCE_METRIC_PREFIX) :]
    if candidate in ALPHA_PERFORMANCE_METRIC_KEYS:
        return key
    return None


def sanitize_alpha_performance_metrics(raw: Mapping[str, Any]) -> dict[str, float]:
    """Return a cleaned metric map containing only known alpha_performance keys."""

    sanitized = default_alpha_performance_metrics()
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        alpha_key = _is_alpha_performance_key(key)
        if alpha_key is None:
            continue
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(numeric):
            continue
        sanitized[alpha_key] = numeric
    return sanitized


def _normalize_per_world(raw: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for world_id, metrics in raw.items():
        if not isinstance(metrics, Mapping):
            continue
        output[str(world_id)] = sanitize_alpha_performance_metrics(metrics)
    return output


def _normalize_per_strategy(raw: Mapping[str, Any]) -> dict[str, dict[str, dict[str, float]]]:
    output: dict[str, dict[str, dict[str, float]]] = {}
    for strategy_id, world_map in raw.items():
        if not isinstance(world_map, Mapping):
            continue
        per_world: dict[str, dict[str, float]] = {}
        for world_id, metrics in world_map.items():
            if not isinstance(metrics, Mapping):
                continue
            per_world[str(world_id)] = sanitize_alpha_performance_metrics(metrics)
        if per_world:
            output[str(strategy_id)] = per_world
    return output


def parse_alpha_metrics_envelope(
    payload: Mapping[str, Any] | None,
) -> Tuple[dict[str, dict[str, float]], dict[str, dict[str, dict[str, float]]]]:
    """Normalize an AlphaMetricsEnvelope-like payload into sanitized maps."""

    if not payload:
        return {}, {}

    per_world_raw = payload.get("per_world") or {}
    per_strategy_raw = payload.get("per_strategy") or {}
    per_world = _normalize_per_world(per_world_raw) if isinstance(per_world_raw, Mapping) else {}
    per_strategy = _normalize_per_strategy(per_strategy_raw) if isinstance(per_strategy_raw, Mapping) else {}
    return per_world, per_strategy


__all__ = [
    "ALPHA_PERFORMANCE_METRIC_KEYS",
    "ALPHA_PERFORMANCE_METRIC_PREFIX",
    "alpha_metric_key",
    "default_alpha_performance_metrics",
    "parse_alpha_metrics_envelope",
    "sanitize_alpha_performance_metrics",
]
