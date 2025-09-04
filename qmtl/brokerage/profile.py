"""Brokerage profiles and security initializer."""

from __future__ import annotations

from dataclasses import dataclass

from .brokerage_model import BrokerageModel
from .interfaces import BuyingPowerModel, FillModel, SlippageModel, FeeModel
from .buying_power import CashBuyingPowerModel
from .fill_models import ImmediateFillModel
from .fees import PerShareFeeModel
from .slippage import SpreadBasedSlippageModel
from .symbols import SymbolPropertiesProvider
from .exchange_hours import ExchangeHoursProvider


@dataclass
class BrokerageProfile:
    buying_power: BuyingPowerModel
    fee: FeeModel
    slippage: SlippageModel
    fill: FillModel
    symbols: SymbolPropertiesProvider | None = None
    hours: ExchangeHoursProvider | None = None

    def build(self) -> BrokerageModel:
        return BrokerageModel(
            self.buying_power,
            self.fee,
            self.slippage,
            self.fill,
            symbols=self.symbols,
            hours=self.hours,
        )


def ibkr_equities_like_profile() -> BrokerageProfile:
    """Construct a simple IBKR-like profile for US equities."""
    return BrokerageProfile(
        buying_power=CashBuyingPowerModel(),
        fee=PerShareFeeModel(fee_per_share=0.005, minimum=1.0),
        slippage=SpreadBasedSlippageModel(spread_fraction=0.5),
        fill=ImmediateFillModel(),
        symbols=SymbolPropertiesProvider(),
        hours=ExchangeHoursProvider(allow_pre_post_market=False, require_regular_hours=True),
    )


class SecurityInitializer:
    """Applies a profile to build brokerage model per security.

    Placeholder for future asset-class-specific wiring.
    """

    def __init__(self, profile: BrokerageProfile) -> None:
        self.profile = profile

    def for_symbol(self, symbol: str) -> BrokerageModel:
        # In future, override tick/lot per symbol here
        return self.profile.build()

