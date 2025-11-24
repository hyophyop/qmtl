from __future__ import annotations

"""Recommended CCXT exchange identifiers and helpers.

This module provides a small enum of commonly used exchanges and a helper to
validate/normalize user-provided identifiers against ``ccxt.exchanges`` when
``ccxt`` is available. The SDK treats ``ccxt`` as optional; in environments
without it, the helper returns the normalized string without validation.
"""

from enum import Enum
import logging

_log = logging.getLogger(__name__)


class CcxtExchange(Enum):
    # Spot (also usable for futures when combined with defaultType=future)
    BINANCE = "binance"
    OKX = "okx"
    BYBIT = "bybit"
    KRAKEN = "kraken"
    COINBASE = "coinbase"
    KUCOIN = "kucoin"
    BITGET = "bitget"
    GATEIO = "gateio"

    # Explicit futures-specific id variants where applicable
    BINANCE_USDM = "binanceusdm"


def normalize_exchange_id(value: str | CcxtExchange) -> str:
    """Return the lowercase CCXT id string for the given enum or string."""
    if isinstance(value, CcxtExchange):
        return value.value
    return str(value).strip().lower()


def ensure_ccxt_exchange(exchange_id: str | CcxtExchange, *, strict: bool = True) -> str:
    """Normalize and (optionally) validate that the id exists in ``ccxt.exchanges``.

    Parameters
    ----------
    exchange_id:
        String id or :class:`CcxtExchange`.
    strict:
        When True, raise ``ValueError`` if ``ccxt`` is available and the id is not
        in ``ccxt.exchanges``. When False, log a warning instead and return id.
    """
    eid = normalize_exchange_id(exchange_id)
    try:  # pragma: no cover - optional dependency import path
        import ccxt
    except Exception:
        # ccxt not installed — skip validation
        return eid

    supported = set(getattr(ccxt, "exchanges", []) or [])
    if supported and eid not in supported:
        msg = f"Exchange id '{eid}' not found in ccxt.exchanges"
        if strict:
            raise ValueError(msg)
        _log.warning(msg)
    return eid


__all__ = ["CcxtExchange", "normalize_exchange_id", "ensure_ccxt_exchange"]
