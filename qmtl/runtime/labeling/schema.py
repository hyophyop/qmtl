"""Shared labeling schema types for delayed-label workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Mapping


class LabelOutcome(str, Enum):
    """Terminal reason for the label resolution."""

    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIMEOUT = "timeout"


class BarrierMode(str, Enum):
    """Barrier representation mode for PT/SL thresholds."""

    PRICE = "price"
    RETURN = "return"


@dataclass(frozen=True)
class BarrierSpec:
    """Frozen profit/stop barriers at entry time."""

    profit_target: float | None
    stop_loss: float | None
    mode: BarrierMode = BarrierMode.RETURN
    frozen_at: datetime | None = None


@dataclass(frozen=True)
class HorizonSpec:
    """Time-based horizon guardrails frozen at entry time."""

    max_duration: timedelta | None = None
    max_bars: int | None = None
    frozen_at: datetime | None = None


@dataclass(frozen=True)
class LabelEvent:
    """Resolved label emitted only after the terminal barrier is hit."""

    symbol: str
    entry_time: datetime
    resolved_time: datetime
    entry_price: float
    resolved_price: float
    outcome: LabelOutcome
    barrier: BarrierSpec
    horizon: HorizonSpec
    realized_return: float
    cost_model_id: str | None = None
    slippage_model_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.resolved_time <= self.entry_time:
            raise ValueError("resolved_time must be > entry_time")
        if self.barrier.frozen_at and self.barrier.frozen_at != self.entry_time:
            raise ValueError("barrier.frozen_at must match entry_time when set")
        if self.horizon.frozen_at and self.horizon.frozen_at != self.entry_time:
            raise ValueError("horizon.frozen_at must match entry_time when set")
