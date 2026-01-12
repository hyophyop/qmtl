"""Cost and slippage models for net-return labeling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Protocol


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def bps_to_return(bps: float) -> float:
    """Convert basis points to return units."""
    return bps / 10_000.0


@dataclass(frozen=True)
class CostContext:
    """Entry-time context available to cost models."""

    entry_time: datetime
    entry_price: float
    side: str
    symbol: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CostEstimate:
    """Return-unit cost estimates frozen at entry time."""

    total_cost: float = 0.0
    min_edge: float = 0.0
    cost_model_id: str | None = None
    slippage_model_id: str | None = None

    def __post_init__(self) -> None:
        _validate_non_negative("total_cost", self.total_cost)
        _validate_non_negative("min_edge", self.min_edge)

    def total_adjustment(self) -> float:
        """Return the total return adjustment applied to gross PnL."""
        return self.total_cost + self.min_edge


class CostModel(Protocol):
    """Protocol for entry-time cost estimates in return units."""

    def estimate(self, context: CostContext) -> CostEstimate:
        """Return a frozen cost estimate for the entry context."""


@dataclass(frozen=True)
class NullCostModel:
    """Default cost model that applies no cost or edge."""

    def estimate(self, context: CostContext) -> CostEstimate:
        return CostEstimate()


@dataclass(frozen=True)
class FixedBpsCostModel:
    """Apply fixed basis-point costs and minimum edge at entry time."""

    total_cost_bps: float
    min_edge_bps: float = 0.0
    cost_model_id: str | None = None
    slippage_model_id: str | None = None

    def __post_init__(self) -> None:
        _validate_non_negative("total_cost_bps", self.total_cost_bps)
        _validate_non_negative("min_edge_bps", self.min_edge_bps)

    def estimate(self, context: CostContext) -> CostEstimate:
        return CostEstimate(
            total_cost=bps_to_return(self.total_cost_bps),
            min_edge=bps_to_return(self.min_edge_bps),
            cost_model_id=self.cost_model_id,
            slippage_model_id=self.slippage_model_id,
        )


__all__ = [
    "CostContext",
    "CostEstimate",
    "CostModel",
    "FixedBpsCostModel",
    "NullCostModel",
    "bps_to_return",
]
