"""Abstract interfaces for brokerage model components."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from abc import ABC, abstractmethod

from .order import Account, Order, Fill


class BuyingPowerModel(ABC):
    """Determine if an order has sufficient buying power."""

    @abstractmethod
    def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
        """Return ``True`` if the account can cover the order cost."""


class FeeModel(ABC):
    """Calculate transaction fees."""

    @abstractmethod
    def calculate(self, order: Order, fill_price: float) -> float:
        """Return the fee for executing ``order`` at ``fill_price``."""


class SlippageModel(ABC):
    """Estimate price impact due to slippage."""

    @abstractmethod
    def apply(self, order: Order, market_price: float) -> float:
        """Return price adjusted for slippage from ``market_price``."""


class FillModel(ABC):
    """Determine fill quantity and base price."""

    @abstractmethod
    def fill(self, order: Order, market_price: float) -> Fill:
        """Return fill details for ``order`` at ``market_price``."""
