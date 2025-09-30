"""Utilities for working with canonical OHLCV node identifiers.

The SDK treats OHLCV history nodes as having the conventional identity
``ohlcv:{exchange}:{symbol}:{timeframe}``.  Several code paths need to build,
inspect, or validate these identifiers.  Centralising the logic in this module
helps us avoid subtle drift between components and provides a single place to
enforce the documented schema.
"""

from __future__ import annotations

from typing import Final

_PREFIX: Final = "ohlcv"

# ``TIMEFRAME_SECONDS`` mirrors the static fallback table used by the CCXT
# fetcher when ``ccxt.parse_timeframe`` is unavailable.  The mapping is exposed
# so consumers can share a consistent view of supported timeframe tokens.
TIMEFRAME_SECONDS: Final[dict[str, int]] = {
    "1s": 1,
    "5s": 5,
    "10s": 10,
    "15s": 15,
    "30s": 30,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
}

SUPPORTED_TIMEFRAMES: Final[frozenset[str]] = frozenset(TIMEFRAME_SECONDS)


def build(exchange: str, symbol: str, timeframe: str) -> str:
    """Construct an OHLCV node identifier.

    Raises
    ------
    ValueError
        If any component is blank, contains a colon, or the timeframe token is
        not recognised.
    """

    exchange_norm = _normalise_component("exchange", exchange)
    symbol_norm = _normalise_component("symbol", symbol)
    timeframe_norm = _normalise_timeframe(timeframe)
    return f"{_PREFIX}:{exchange_norm}:{symbol_norm}:{timeframe_norm}"


def parse(node_id: str) -> tuple[str, str, str] | None:
    """Parse a canonical OHLCV node identifier.

    Returns ``None`` when ``node_id`` is not an OHLCV identifier in the
    expected ``ohlcv:{exchange}:{symbol}:{timeframe}`` format.
    """

    if not isinstance(node_id, str):  # defensive guard; mirrors ``split`` API
        return None

    trimmed = node_id.strip()
    if not trimmed:
        return None

    parts = trimmed.split(":")
    if len(parts) != 4 or parts[0] != _PREFIX:
        return None

    exchange, symbol, timeframe = parts[1], parts[2], parts[3]
    if not exchange or not symbol or not timeframe:
        return None
    return exchange, symbol, timeframe


def validate(node_id: str) -> None:
    """Validate that ``node_id`` follows the canonical OHLCV schema.

    Raises
    ------
    ValueError
        If the identifier is malformed or includes unsupported components.
    """

    parsed = parse(node_id)
    if not parsed:
        raise ValueError(
            f"Invalid OHLCV node_id {node_id!r}; expected 'ohlcv:{{exchange}}:{{symbol}}:{{timeframe}}'"
        )

    exchange, symbol, timeframe = parsed
    for name, value in ("exchange", exchange), ("symbol", symbol):
        if not value.strip():
            raise ValueError(f"OHLCV node_id {node_id!r} missing {name} component")
        if ":" in value:
            raise ValueError(
                f"OHLCV node_id {node_id!r} contains ':' in the {name} component"
            )

    timeframe_norm = timeframe.strip()
    if not timeframe_norm:
        raise ValueError(f"OHLCV node_id {node_id!r} missing timeframe component")
    if timeframe_norm not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported OHLCV timeframe '{timeframe_norm}' in node_id {node_id!r}"
        )


def _normalise_component(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{name} component cannot be empty")
    if ":" in trimmed:
        raise ValueError(f"{name} component cannot contain ':'")
    return trimmed


def _normalise_timeframe(timeframe: str) -> str:
    if not isinstance(timeframe, str):
        raise TypeError(
            f"timeframe must be a string, got {type(timeframe).__name__}"
        )
    trimmed = timeframe.strip()
    if not trimmed:
        raise ValueError("timeframe component cannot be empty")
    if trimmed not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe token: {trimmed}")
    return trimmed


__all__ = [
    "TIMEFRAME_SECONDS",
    "SUPPORTED_TIMEFRAMES",
    "build",
    "parse",
    "validate",
]

