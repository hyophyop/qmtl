"""Unified mode concept for QMTL v2.0.

This module provides the simplified mode interface that replaces the
complex 4-level ExecutionDomain mapping:

    effective_mode (WS) → execution_domain (Gateway) → behavior (SDK)

With QMTL v2.0, users only need to understand 3 modes:
- backtest: Historical data simulation (used for auto-evaluation)
- paper: Real-time data, simulated orders
- live: Real-time data, real orders

Internal mapping is preserved for backward compatibility with existing
infrastructure, but users should only interact with these 3 modes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

__all__ = [
    "Mode",
    "mode_to_execution_domain",
    "execution_domain_to_mode",
    "effective_mode_to_mode",
    "is_orders_enabled",
    "is_real_time_data",
]


class Mode(StrEnum):
    """User-facing execution modes for QMTL v2.0.
    
    Only 3 modes are exposed to users:
    - BACKTEST: Historical data simulation (used for auto-evaluation)
    - PAPER: Real-time data, simulated orders  
    - LIVE: Real-time data, real orders
    
    These map to internal execution domains transparently.
    """
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


# Internal mapping: Mode → execution_domain
_MODE_TO_DOMAIN = {
    Mode.BACKTEST: "backtest",
    Mode.PAPER: "dryrun",
    Mode.LIVE: "live",
}

# Internal mapping: execution_domain → Mode
_DOMAIN_TO_MODE = {
    "backtest": Mode.BACKTEST,
    "dryrun": Mode.PAPER,
    "live": Mode.LIVE,
    "shadow": Mode.BACKTEST,  # Shadow maps to backtest for safety
    "default": Mode.BACKTEST,
}

# Internal mapping: effective_mode (from WS) → Mode
_EFFECTIVE_MODE_TO_MODE = {
    "validate": Mode.BACKTEST,
    "compute-only": Mode.BACKTEST,
    "paper": Mode.PAPER,
    "live": Mode.LIVE,
    "shadow": Mode.BACKTEST,  # Shadow treated as backtest for users
}


def mode_to_execution_domain(mode: Mode | str) -> str:
    """Convert user-facing mode to internal execution domain.
    
    This is used internally when communicating with Gateway/WS.
    Users should not need to call this directly.
    
    Parameters
    ----------
    mode : Mode | str
        User-facing mode (backtest/paper/live)
    
    Returns
    -------
    str
        Internal execution domain (backtest/dryrun/live)
    
    Examples
    --------
    >>> mode_to_execution_domain(Mode.PAPER)
    'dryrun'
    >>> mode_to_execution_domain("live")
    'live'
    """
    if isinstance(mode, str):
        mode = Mode(mode.lower())
    return _MODE_TO_DOMAIN.get(mode, "backtest")


def execution_domain_to_mode(domain: str | None) -> Mode:
    """Convert internal execution domain to user-facing mode.
    
    This is used when receiving data from Gateway/WS to present
    to users in a simplified way.
    
    Parameters
    ----------
    domain : str | None
        Internal execution domain
    
    Returns
    -------
    Mode
        User-facing mode
    
    Examples
    --------
    >>> execution_domain_to_mode("dryrun")
    <Mode.PAPER: 'paper'>
    >>> execution_domain_to_mode(None)
    <Mode.BACKTEST: 'backtest'>
    """
    if domain is None:
        return Mode.BACKTEST
    return _DOMAIN_TO_MODE.get(domain.lower(), Mode.BACKTEST)


def effective_mode_to_mode(effective_mode: str | None) -> Mode:
    """Convert WorldService effective_mode to user-facing mode.
    
    WorldService emits effective_mode (validate/compute-only/paper/live).
    This function converts it to the simplified user-facing mode.
    
    Parameters
    ----------
    effective_mode : str | None
        WorldService effective_mode value
    
    Returns
    -------
    Mode
        User-facing mode
    
    Examples
    --------
    >>> effective_mode_to_mode("validate")
    <Mode.BACKTEST: 'backtest'>
    >>> effective_mode_to_mode("paper")
    <Mode.PAPER: 'paper'>
    """
    if effective_mode is None:
        return Mode.BACKTEST
    return _EFFECTIVE_MODE_TO_MODE.get(effective_mode.lower(), Mode.BACKTEST)


def is_orders_enabled(mode: Mode | str) -> bool:
    """Check if orders are enabled for a mode.
    
    Parameters
    ----------
    mode : Mode | str
        Execution mode
    
    Returns
    -------
    bool
        True if real orders are enabled (live mode only)
    """
    if isinstance(mode, str):
        mode = Mode(mode.lower())
    return mode == Mode.LIVE


def is_real_time_data(mode: Mode | str) -> bool:
    """Check if mode uses real-time data.
    
    Parameters
    ----------
    mode : Mode | str
        Execution mode
    
    Returns
    -------
    bool
        True if real-time data is used (paper or live)
    """
    if isinstance(mode, str):
        mode = Mode(mode.lower())
    return mode in (Mode.PAPER, Mode.LIVE)


def normalize_mode(value: Any) -> Mode:
    """Normalize any mode-like value to Mode enum.
    
    Handles legacy values, aliases, and various input formats.
    
    Parameters
    ----------
    value : Any
        Mode value (string, Mode enum, etc.)
    
    Returns
    -------
    Mode
        Normalized Mode enum value
    
    Examples
    --------
    >>> normalize_mode("BACKTEST")
    <Mode.BACKTEST: 'backtest'>
    >>> normalize_mode("dryrun")
    <Mode.PAPER: 'paper'>
    >>> normalize_mode(Mode.LIVE)
    <Mode.LIVE: 'live'>
    """
    if isinstance(value, Mode):
        return value
    
    if not isinstance(value, str):
        return Mode.BACKTEST
    
    lowered = value.strip().lower()
    
    # Direct Mode values
    if lowered in ("backtest", "backtesting", "offline", "sandbox", "validate"):
        return Mode.BACKTEST
    if lowered in ("paper", "paper_trade", "papertrade", "dryrun", "dry_run", "sim", "simulation"):
        return Mode.PAPER
    if lowered in ("live", "prod", "production", "real"):
        return Mode.LIVE
    
    # Try execution_domain mapping
    mode = _DOMAIN_TO_MODE.get(lowered)
    if mode is not None:
        return mode
    
    # Try effective_mode mapping
    mode = _EFFECTIVE_MODE_TO_MODE.get(lowered)
    if mode is not None:
        return mode
    
    # Default to backtest
    return Mode.BACKTEST
