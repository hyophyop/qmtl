"""Shared execution utilities for execution nodes across packages."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Tuple

from qmtl.brokerage import Account, BrokerageModel, OrderType, TimeInForce
from qmtl.common.pretrade import RejectionReason
from qmtl.sdk.order_gate import Activation
from qmtl.sdk.portfolio import (
    Portfolio,
    order_percent,
    order_target_percent,
    order_value,
)
from qmtl.sdk.pretrade import check_pretrade


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def run_pretrade_checks(
    order: Mapping[str, Any],
    *,
    activation_map: Mapping[str, Activation],
    brokerage: BrokerageModel,
    account: Account,
    default_order_type: OrderType = OrderType.MARKET,
    default_tif: TimeInForce = TimeInForce.DAY,
) -> Tuple[bool, dict[str, Any]]:
    """Return the outcome of the shared pre-trade checks.

    The function copies ``order`` to avoid mutating the caller's payload. When
    all checks pass the sanitized order dictionary is returned. Otherwise a
    structured rejection payload is produced.
    """

    symbol = order["symbol"]
    quantity = _coerce_int(order["quantity"])
    price = _coerce_float(order.get("price"))
    order_type = order.get("order_type", default_order_type)
    tif = order.get("tif", default_tif)
    limit_price = _coerce_float(order.get("limit_price"))
    stop_price = _coerce_float(order.get("stop_price"))

    result = check_pretrade(
        activation_map=activation_map,
        brokerage=brokerage,
        account=account,
        symbol=str(symbol),
        quantity=quantity if quantity is not None else 0,
        price=price if price is not None else 0.0,
        order_type=order_type,
        tif=tif,
        limit_price=limit_price,
        stop_price=stop_price,
    )

    if result.allowed:
        return True, dict(order)

    reason = result.reason.value if getattr(result, "reason", None) else RejectionReason.UNKNOWN.value
    return False, {"rejected": True, "reason": reason}


def apply_sizing(
    order: Mapping[str, Any],
    portfolio: Portfolio,
    *,
    weight_fn: Callable[[Mapping[str, Any]], float] | None = None,
) -> dict[str, Any] | None:
    """Return a sized order dictionary or ``None`` when insufficient data."""

    sized = dict(order)
    if "quantity" in sized:
        return sized

    price = _coerce_float(sized.get("price"))
    if price is None:
        return None

    symbol = sized.get("symbol")
    if symbol is None:
        return None

    qty: float | None = None
    if "value" in sized:
        qty = order_value(symbol, _coerce_float(sized["value"]) or 0.0, price)
    elif "percent" in sized:
        percent = _coerce_float(sized["percent"])
        if percent is not None:
            qty = order_percent(portfolio, symbol, percent, price)
    elif "target_percent" in sized:
        target = _coerce_float(sized["target_percent"])
        if target is not None:
            qty = order_target_percent(portfolio, symbol, target, price)

    if qty is None:
        return sized

    if weight_fn is not None:
        try:
            weight = float(weight_fn(sized))
            if weight < 0.0:
                weight = 0.0
            elif weight > 1.0:
                weight = 1.0
            qty *= weight
        except Exception:  # pragma: no cover - defensive guard
            pass

    sized["quantity"] = qty
    return sized


__all__ = ["run_pretrade_checks", "apply_sizing"]
