"""Standardized pre-trade rejection reasons and helpers.

# Source: docs/ko/architecture/gateway.md
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
    for keywords, reason in (
        (("market is closed", "hours"), RejectionReason.MARKET_CLOSED),
        (("shortable",), RejectionReason.NOT_SHORTABLE),
        (("tick", "lot", "symbol", "price"), RejectionReason.SYMBOL_VALIDATION_FAILED),
        (("buying power", "sufficient"), RejectionReason.INSUFFICIENT_BUYING_POWER),
        (("order",), RejectionReason.INVALID_ORDER),
    ):
        if any(token in msg for token in keywords):
            return reason
    return RejectionReason.UNKNOWN


__all__ = ["RejectionReason", "categorize_exception"]
