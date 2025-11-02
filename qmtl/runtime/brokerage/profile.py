"""Brokerage profiles and security initializer."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Optional

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

    def override(self, **kwargs: object) -> "BrokerageProfile":
        """Return a copy of this profile with selected fields overridden.

        Examples
        --------
        >>> profile.override(fee=new_fee_model)
        """
        return replace(self, **kwargs)


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
    """Build brokerage models with per-symbol or per-asset-class overrides.

    Parameters
    ----------
    profile:
        Default profile used when no overrides match ``symbol``.
    profiles_by_symbol:
        Exact symbol bindings to profiles.
    profiles_by_asset_class:
        Profiles keyed by asset class string, used when ``classify`` returns a
        matching key.
    classify:
        Optional callable mapping ``symbol`` to an asset class string.
    override:
        Optional hook executed with the built :class:`BrokerageModel` and
        ``symbol``. May mutate or return a replacement model.
    """

    def __init__(
        self,
        profile: BrokerageProfile,
        *,
        profiles_by_symbol: Mapping[str, BrokerageProfile] | None = None,
        profiles_by_asset_class: Mapping[str, BrokerageProfile] | None = None,
        classify: Optional[Callable[[str], str]] = None,
        override: Optional[Callable[[BrokerageModel, str], Optional[BrokerageModel]]] = None,
    ) -> None:
        self.default_profile = profile
        self.profiles_by_symbol = dict(profiles_by_symbol or {})
        self.profiles_by_asset_class = dict(profiles_by_asset_class or {})
        self.classify = classify
        self.override = override

    def for_symbol(self, symbol: str) -> BrokerageModel:
        profile = self.profiles_by_symbol.get(symbol)
        if profile is None and self.classify is not None:
            asset_class = self.classify(symbol)
            profile = self.profiles_by_asset_class.get(asset_class)
        if profile is None:
            profile = self.default_profile
        model = profile.build()
        if self.override is not None:
            replacement = self.override(model, symbol)
            if replacement is not None:
                model = replacement
        return model

