"""Backtest fill engine powered by BrokerageModel (unified with ExecutionModel).

# Source: docs/architecture/lean_brokerage_model.md

This engine provides an adapter that can simulate executions using the
pluggable QMTL ``BrokerageModel`` while producing the same shape as the
existing SDK ``ExecutionModel`` (i.e., returning ``ExecutionFill``).

The pricing logic mirrors the simplified ``ExecutionModel`` so results
are identical given the same inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qmtl.brokerage import (
    BrokerageModel,
    Order as BrOrder,
    OrderType as BrOrderType,
    TimeInForce as BrTIF,
    Account,
)
from qmtl.brokerage.fees import PercentFeeModel
from qmtl.brokerage.slippage import NullSlippageModel
from qmtl.brokerage.fill_models import UnifiedFillModel
from .execution_modeling import (
    ExecutionFill,
    MarketData,
    OrderSide,
    OrderType,
)


@dataclass
class ExecCompatParams:
    commission_rate: float = 0.001
    commission_minimum: float = 1.0
    base_slippage_bps: float = 2.0
    market_impact_coeff: float = 0.1
    latency_ms: int = 100


def _map_order_type(t: OrderType) -> BrOrderType:
    return {
        OrderType.MARKET: BrOrderType.MARKET,
        OrderType.LIMIT: BrOrderType.LIMIT,
        OrderType.STOP: BrOrderType.STOP,
        OrderType.STOP_LIMIT: BrOrderType.STOP_LIMIT,
    }[t]


class BrokerageBacktestEngine:
    """Simulate executions using a ``BrokerageModel`` and return ``ExecutionFill``."""

    def __init__(
        self,
        brokerage: BrokerageModel,
        *,
        account: Optional[Account] = None,
        latency_ms: int = 100,
        compat_params: Optional[ExecCompatParams] = None,
    ) -> None:
        self._brokerage = brokerage
        self._account = account or Account(cash=10_000_000.0)
        self._compat = compat_params or ExecCompatParams(latency_ms=latency_ms)

    def _base_price(self, order_type: OrderType, side: OrderSide, requested: float, md: MarketData) -> float:
        if order_type == OrderType.MARKET:
            return md.ask if side == OrderSide.BUY else md.bid
        return requested

    def simulate_execution(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        requested_price: float,
        market_data: MarketData,
        timestamp: int,
    ) -> ExecutionFill:
        """Simulate execution via brokerage components.

        This reproduces the SDK ExecutionModel pricing (base + slippage
        formula) and uses ``PercentFeeModel`` with the same rate/minimum
        for fees to ensure output parity.
        """

        # Build brokerage order (quantity sign indicates side)
        signed_qty = int(quantity if side == OrderSide.BUY else -quantity)
        br_order = BrOrder(
            symbol=symbol,
            quantity=signed_qty,
            price=requested_price,
            type=_map_order_type(order_type),
            tif=BrTIF.DAY,
        )

        # Determine base price like ExecutionModel
        base_price = self._base_price(order_type, side, requested_price, market_data)

        # Compute simplified slippage consistent with ExecutionModel
        base_slip = market_data.mid_price * (self._compat.base_slippage_bps / 10000.0)
        if market_data.volume > 0:
            volume_ratio = quantity / market_data.volume
            impact = self._compat.market_impact_coeff * volume_ratio * market_data.mid_price
        else:
            impact = 0.0
        spread_cost = (market_data.spread / 2.0) if order_type == OrderType.MARKET else 0.0
        slippage = base_slip + impact + spread_cost
        slippage = slippage if side == OrderSide.BUY else -slippage

        # Fill price and fee (use brokerage fee model if available, else percent-based)
        fill_price = base_price + slippage

        # Fees using brokerage fee model if it's Percent-like; otherwise approximate
        try:
            fee = self._brokerage.fee_model.calculate(br_order, fill_price)  # type: ignore[attr-defined]
        except Exception:
            fee = PercentFeeModel(rate=self._compat.commission_rate, minimum=self._compat.commission_minimum).calculate(br_order, fill_price)

        # Update account cash similar to BrokerageModel immediate settlement
        cost = fill_price * signed_qty + fee
        self._account.cash -= cost

        return ExecutionFill(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            requested_price=requested_price,
            fill_price=fill_price,
            fill_time=timestamp + self._compat.latency_ms,
            commission=fee,
            slippage=slippage,
            market_impact=abs(impact),
        )


def make_brokerage_model_for_compat(params: ExecCompatParams) -> BrokerageModel:
    """Create a minimal brokerage model aligned with ExecutionModel params.

    - Fees: Percent rate + minimum
    - Slippage: disabled (slippage is applied in the adapter for parity)
    - Fill model: UnifiedFillModel (covers market/limit/stop/stop-limit)
    - Buying power: injected by caller if needed; default allows all (via lambda)
    """
    from qmtl.brokerage.simple import CashBuyingPowerModel

    class _AllBP(CashBuyingPowerModel):
        def has_sufficient_buying_power(self, account: Account, order: BrOrder) -> bool:  # type: ignore[override]
            return True

    brokerage = BrokerageModel(
        buying_power_model=_AllBP(),
        fee_model=PercentFeeModel(rate=params.commission_rate, minimum=params.commission_minimum),
        slippage_model=NullSlippageModel(),  # slippage accounted in adapter for parity
        fill_model=UnifiedFillModel(),
    )
    return brokerage


__all__ = [
    "BrokerageBacktestEngine",
    "ExecCompatParams",
    "make_brokerage_model_for_compat",
]

