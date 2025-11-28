"""Shared execution utilities for execution nodes across packages."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Tuple, cast

from qmtl.runtime.brokerage import Account, BrokerageModel, OrderType, TimeInForce
from qmtl.foundation.common.pretrade import RejectionReason
from qmtl.runtime.sdk.order_gate import Activation
from qmtl.runtime.sdk.portfolio import (
    Portfolio,
    order_percent,
    order_target_percent,
    order_value,
)
from qmtl.runtime.sdk.pretrade import check_pretrade
from qmtl.runtime.pipeline.order_types import OrderRejection, SizedOrder


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def run_pretrade_checks(
    order: Mapping[str, Any],
    *,
    activation_map: Mapping[str, Activation],
    brokerage: BrokerageModel,
    account: Account,
    default_order_type: OrderType = OrderType.MARKET,
    default_tif: TimeInForce = TimeInForce.DAY,
) -> Tuple[bool, SizedOrder | OrderRejection]:
    """Return the outcome of the shared pre-trade checks.

    The function copies ``order`` to avoid mutating the caller's payload. When
    all checks pass the sanitized order dictionary is returned. Otherwise a
    structured rejection payload is produced.
    """

    symbol = order["symbol"]
    quantity = _coerce_float(order["quantity"])
    price = _coerce_float(order.get("price"))
    order_type = order.get("order_type", default_order_type)
    tif = order.get("tif", default_tif)
    limit_price = _coerce_float(order.get("limit_price"))
    stop_price = _coerce_float(order.get("stop_price"))

    quantity_for_check = int(quantity) if quantity is not None else 0
    price_for_check = price if price is not None else 0.0

    result = check_pretrade(
        activation_map=activation_map,
        brokerage=brokerage,
        account=account,
        symbol=str(symbol),
        quantity=quantity_for_check,
        price=price_for_check,
        order_type=order_type,
        tif=tif,
        limit_price=limit_price,
        stop_price=stop_price,
    )

    sanitized = dict(order)
    if quantity is not None:
        sanitized["quantity"] = quantity
    if price is not None:
        sanitized["price"] = price

    if result.allowed:
        return True, cast(SizedOrder, sanitized)

    reason = result.reason.value if result.reason is not None else RejectionReason.UNKNOWN.value
    return False, {"rejected": True, "reason": reason}


def apply_sizing(
    order: Mapping[str, Any],
    portfolio: Portfolio,
    *,
    weight_fn: Callable[[Mapping[str, Any]], float] | None = None,
) -> SizedOrder | None:
    """Return a sized order dictionary or ``None`` when insufficient data."""

    sized: dict[str, Any] = dict(order)

    price = _coerce_float(sized.get("price"))
    if price is None:
        return None
    sized["price"] = price

    symbol = sized.get("symbol")
    if symbol is None:
        return None

    if "quantity" in sized:
        quantity = _coerce_float(sized.get("quantity"))
        if quantity is None:
            return None
        sized["quantity"] = quantity
        return cast(SizedOrder, sized)

    qty = _resolve_quantity(sized, portfolio, symbol, price)
    if qty is None:
        return None

    sized["quantity"] = _apply_weight(qty, sized, weight_fn)
    return cast(SizedOrder, sized)


def _resolve_quantity(
    sized: Mapping[str, Any], portfolio: Portfolio, symbol: Any, price: float
) -> float | None:
    calculators: tuple[tuple[str, Callable[[float], float | None]], ...] = (
        ("value", lambda amount: order_value(symbol, amount, price)),
        ("percent", lambda percent: order_percent(portfolio, symbol, percent, price)),
        (
            "target_percent",
            lambda target: order_target_percent(portfolio, symbol, target, price),
        ),
    )

    for key, calc in calculators:
        if key not in sized:
            continue
        candidate = _coerce_float(sized[key])
        if candidate is None:
            continue
        return calc(candidate)

    return None


def _apply_weight(
    qty: float, sized: Mapping[str, Any], weight_fn: Callable[[Mapping[str, Any]], float] | None
) -> float:
    if weight_fn is None:
        return qty

    try:
        weight = float(weight_fn(sized))
    except Exception:  # pragma: no cover - defensive guard
        return qty

    bounded = max(0.0, min(weight, 1.0))
    return qty * bounded


__all__ = ["run_pretrade_checks", "apply_sizing"]
