from __future__ import annotations

import re
from typing import Any, Tuple

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


def normalize_context_value(value: Any | None) -> str | None:
    """Normalize raw meta values to stripped strings."""

    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def resolve_execution_domain(value: str | None) -> str | None:
    """Map execution domain aliases to canonical tokens."""

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


def evaluate_safe_mode(
    execution_domain: str | None, as_of: str | None
) -> Tuple[str | None, bool, str | None, bool]:
    """Determine whether the compute context must enter safe mode."""

    downgraded = False
    downgrade_reason: str | None = None
    safe_mode = False

    if execution_domain in {"backtest", "dryrun"} and not as_of:
        downgraded = True
        downgrade_reason = "missing_as_of"
        safe_mode = True
        execution_domain = "backtest"

    return execution_domain, downgraded, downgrade_reason, safe_mode


__all__ = [
    "evaluate_safe_mode",
    "normalize_context_value",
    "resolve_execution_domain",
]
