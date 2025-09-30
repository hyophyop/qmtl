"""Example strategy demonstrating RiskManager usage."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from qmtl.runtime.sdk.risk_management import PositionInfo, RiskManager, RiskViolation


def enforce_position_limit(
    *,
    symbol: str,
    proposed_quantity: float,
    price: float,
    portfolio_value: float,
    current_positions: Optional[Dict[str, PositionInfo]] = None,
) -> Tuple[bool, Optional[RiskViolation], float]:
    """Validate a trade against position size limits.

    Parameters
    ----------
    symbol : str
        Asset identifier for the trade.
    proposed_quantity : float
        Desired number of units to trade.
    price : float
        Current asset price.
    portfolio_value : float
        Total value of the portfolio.
    current_positions : dict, optional
        Existing positions keyed by symbol.

    Returns
    -------
    tuple
        (is_valid, violation_if_any, adjusted_quantity)
    """
    positions = current_positions or {}
    risk_mgr = RiskManager(position_size_limit_pct=0.10)
    return risk_mgr.validate_position_size(
        symbol=symbol,
        proposed_quantity=proposed_quantity,
        current_price=price,
        portfolio_value=portfolio_value,
        current_positions=positions,
    )
