"""SDK pre-trade validation wrapper with standardized reasons + metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from qmtl.common.pretrade import RejectionReason, categorize_exception
from qmtl.brokerage import BrokerageModel, Order, OrderType, TimeInForce, Account
from . import metrics as sdk_metrics
from .order_gate import Activation, gate_order


@dataclass(frozen=True)
class PreTradeCheckResult:
    allowed: bool
    reason: Optional[RejectionReason] = None


def check_pretrade(
    *,
    activation_map: Mapping[str, Activation],
    brokerage: BrokerageModel,
    account: Account,
    symbol: str,
    quantity: int,
    price: float,
    order_type: OrderType = OrderType.MARKET,
    tif: TimeInForce = TimeInForce.DAY,
    limit_price: float | None = None,
    stop_price: float | None = None,
    record_metrics: bool = True,
) -> PreTradeCheckResult:
    """Run activation + brokerage checks and record metrics.

    Returns a structured result with standardized reason codes when rejected.
    """
    if record_metrics:
        sdk_metrics.record_pretrade_attempt()

    # Activation gating
    allowed, reason = gate_order(activation_map, symbol)
    if not allowed:
        code = (
            RejectionReason.ACTIVATION_DISABLED
            if (reason and "disabled" in reason)
            else RejectionReason.ACTIVATION_UNKNOWN
        )
        if record_metrics:
            sdk_metrics.record_pretrade_rejection(code.value)
        return PreTradeCheckResult(False, code)

    # Brokerage checks
    order = Order(
        symbol=symbol,
        quantity=quantity,
        price=price,
        type=order_type,
        tif=tif,
        limit_price=limit_price,
        stop_price=stop_price,
    )
    try:
        ok = brokerage.can_submit_order(account, order)
    except Exception as exc:  # Hours/shortable/symbol checks raise
        code = categorize_exception(exc)
        if record_metrics:
            sdk_metrics.record_pretrade_rejection(code.value)
        return PreTradeCheckResult(False, code)
    if not ok:
        code = RejectionReason.INSUFFICIENT_BUYING_POWER
        if record_metrics:
            sdk_metrics.record_pretrade_rejection(code.value)
        return PreTradeCheckResult(False, code)

    return PreTradeCheckResult(True, None)


__all__ = ["check_pretrade", "PreTradeCheckResult"]

