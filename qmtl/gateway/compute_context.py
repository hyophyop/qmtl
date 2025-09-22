"""Shared helpers for strategy compute context normalization."""

from __future__ import annotations

import re
from typing import Any, Mapping

from . import metrics as gw_metrics

_BACKTEST_TOKENS = {
    "backtest",
    "backtesting",
    "compute",
    "computeonly",
    "offline",
    "sandbox",
    "sim",
    "simulation",
    "simulated",
    "validate",
    "validation",
}
_DRYRUN_TOKENS = {
    "dryrun",
    "dryrunmode",
    "papermode",
    "paper",
    "papertrade",
    "papertrading",
    "papertrader",
}
_LIVE_TOKENS = {"live", "prod", "production"}
_SHADOW_TOKENS = {"shadow"}


def _normalize_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    if isinstance(value, bytes):
        text = value.decode().strip()
        return text or None
    return None


def _resolve_execution_domain(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.lower()
    segments = re.split(r"[/:]", lowered)
    for segment in segments:
        token = re.sub(r"[\s_-]+", "", segment)
        if token in _BACKTEST_TOKENS:
            return "backtest"
        if token in _DRYRUN_TOKENS:
            return "dryrun"
        if token in _LIVE_TOKENS:
            return "live"
        if token in _SHADOW_TOKENS:
            return "shadow"
    return lowered


def build_strategy_compute_context(
    meta: Mapping[str, Any] | None,
    *,
    emit_metrics: bool = True,
) -> tuple[dict[str, str | None], bool, str | None]:
    """Return normalized compute context for a strategy submission."""

    meta = meta or {}
    raw_domain = _normalize_value(meta.get("execution_domain")) if meta else None
    execution_domain = _resolve_execution_domain(raw_domain)
    as_of = _normalize_value(meta.get("as_of") if meta else None)
    partition = _normalize_value(meta.get("partition") if meta else None)
    dataset_fingerprint = _normalize_value(meta.get("dataset_fingerprint") if meta else None)

    downgraded = False
    downgrade_reason: str | None = None
    if execution_domain in {"backtest", "dryrun"} and not as_of:
        downgraded = True
        downgrade_reason = "missing_as_of"
        if emit_metrics:
            gw_metrics.strategy_compute_context_downgrade_total.labels(reason=downgrade_reason).inc()
        if execution_domain == "dryrun":
            execution_domain = "backtest"

    context: dict[str, str | None] = {
        "execution_domain": execution_domain,
        "as_of": as_of,
        "partition": partition,
        "dataset_fingerprint": dataset_fingerprint,
    }
    return context, downgraded, downgrade_reason


__all__ = ["build_strategy_compute_context"]
