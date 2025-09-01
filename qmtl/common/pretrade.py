"""Standardized pre-trade rejection reasons and helpers.

# Source: docs/architecture/gateway.md
"""

from __future__ import annotations

from enum import Enum


class RejectionReason(str, Enum):
    ACTIVATION_DISABLED = "activation_disabled"
    ACTIVATION_UNKNOWN = "activation_unknown"
    SYMBOL_VALIDATION_FAILED = "symbol_validation_failed"
    MARKET_CLOSED = "market_closed"
    NOT_SHORTABLE = "not_shortable"
    INSUFFICIENT_BUYING_POWER = "insufficient_buying_power"
    INVALID_ORDER = "invalid_order"
    UNKNOWN = "unknown"


def categorize_exception(exc: Exception) -> RejectionReason:
    """Best-effort mapping from validation exceptions to a reason code."""
    msg = str(exc).lower()
    if "market is closed" in msg or "hours" in msg:
        return RejectionReason.MARKET_CLOSED
    if "shortable" in msg:
        return RejectionReason.NOT_SHORTABLE
    if "tick" in msg or "lot" in msg or "symbol" in msg or "price" in msg:
        return RejectionReason.SYMBOL_VALIDATION_FAILED
    if "buying power" in msg or "sufficient" in msg:
        return RejectionReason.INSUFFICIENT_BUYING_POWER
    if "order" in msg:
        return RejectionReason.INVALID_ORDER
    return RejectionReason.UNKNOWN


__all__ = ["RejectionReason", "categorize_exception"]

