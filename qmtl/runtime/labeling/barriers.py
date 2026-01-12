"""Barrier specification helpers for delayed-label workflows."""

from __future__ import annotations

from datetime import datetime

from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec

_SIDE_ALIASES = {
    "long": "long",
    "short": "short",
    "buy": "long",
    "sell": "short",
}


def _normalize_side(side: str) -> str:
    if not side:
        raise ValueError("side is required")
    normalized = _SIDE_ALIASES.get(side.lower())
    if normalized is None:
        raise ValueError(f"side must be one of {sorted(_SIDE_ALIASES)}")
    return normalized


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def _scale_multiplier(multiplier: float | None, base: float, name: str) -> float | None:
    if multiplier is None:
        return None
    _validate_non_negative(name, multiplier)
    return base * multiplier


def _price_barrier(price: float, delta: float | None, side: str, *, is_profit: bool) -> float | None:
    if delta is None:
        return None
    if side == "long":
        return price + delta if is_profit else price - delta
    return price - delta if is_profit else price + delta


def volatility_scaled_barrier_spec(
    *,
    price: float,
    sigma: float,
    profit_multiplier: float | None,
    stop_multiplier: float | None,
    side: str,
    mode: BarrierMode = BarrierMode.PRICE,
    frozen_at: datetime | None = None,
) -> BarrierSpec:
    """Return a volatility-scaled :class:`BarrierSpec` in price or return mode.

    ``sigma`` is expected to be a return volatility (e.g., stdev of returns),
    making ``sigma * price`` the base price distance.
    """
    _validate_non_negative("price", price)
    _validate_non_negative("sigma", sigma)
    normalized_side = _normalize_side(side)
    if mode == BarrierMode.PRICE:
        base = price * sigma
        profit_delta = _scale_multiplier(profit_multiplier, base, "profit_multiplier")
        stop_delta = _scale_multiplier(stop_multiplier, base, "stop_multiplier")
        profit_target = _price_barrier(price, profit_delta, normalized_side, is_profit=True)
        stop_loss = _price_barrier(price, stop_delta, normalized_side, is_profit=False)
    elif mode == BarrierMode.RETURN:
        if profit_multiplier is not None:
            _validate_non_negative("profit_multiplier", profit_multiplier)
            profit_target = profit_multiplier * sigma
        else:
            profit_target = None
        if stop_multiplier is not None:
            _validate_non_negative("stop_multiplier", stop_multiplier)
            stop_loss = stop_multiplier * sigma
        else:
            stop_loss = None
    else:
        raise ValueError(
            f"mode must be one of {', '.join(mode.value for mode in BarrierMode)}"
        )

    return BarrierSpec(
        profit_target=profit_target,
        stop_loss=stop_loss,
        mode=mode,
        frozen_at=frozen_at,
    )


__all__ = ["volatility_scaled_barrier_spec"]
