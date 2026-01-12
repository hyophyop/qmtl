"""Horizon resolvers for time-barrier labeling workflows.

All horizon specs are resolved using entry-time context and past-only inputs,
then frozen at ``entry_time`` to prevent leakage from future data.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from qmtl.runtime.labeling.schema import HorizonSpec


@dataclass(frozen=True)
class HorizonContext:
    """Context available at entry time for resolving a horizon."""

    entry_time: datetime
    past_values: Sequence[float] | None = None
    event_timedelta: timedelta | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


class HorizonResolver(Protocol):
    """Interface for resolving a horizon from entry-time context."""

    def resolve(self, context: HorizonContext) -> HorizonSpec:
        """Return a frozen horizon spec for the given entry context."""


def estimate_half_life(values: Sequence[float]) -> float:
    """Estimate the half-life (in events) from a mean-reverting series."""
    if len(values) < 3:
        raise ValueError("values must include at least 3 points")
    x = values[:-1]
    delta = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    x_mean = statistics.fmean(x)
    delta_mean = statistics.fmean(delta)
    variance = sum((item - x_mean) ** 2 for item in x)
    if variance <= 0:
        raise ValueError("values must have non-zero variance")
    covariance = sum(
        (item - x_mean) * (delta_item - delta_mean)
        for item, delta_item in zip(x, delta)
    )
    beta = covariance / variance
    if beta >= 0 or (1 + beta) <= 0:
        raise ValueError("values do not imply mean reversion")
    return -math.log(2) / math.log(1 + beta)


@dataclass(frozen=True)
class EventCountHorizonResolver:
    """Resolve a fixed event-count horizon (tick/volume/dollar bars)."""

    max_events: int

    def __post_init__(self) -> None:
        if self.max_events <= 0:
            raise ValueError("max_events must be > 0")

    def resolve(self, context: HorizonContext) -> HorizonSpec:
        return HorizonSpec(
            max_bars=self.max_events,
            frozen_at=context.entry_time,
        )


@dataclass(frozen=True)
class HalfLifeHorizonResolver:
    """Resolve a horizon by scaling an estimated half-life from past values."""

    multiplier: float = 1.0
    min_events: int = 1
    max_events: int | None = None
    estimator: Callable[[Sequence[float]], float] = estimate_half_life

    def __post_init__(self) -> None:
        if self.multiplier <= 0:
            raise ValueError("multiplier must be > 0")
        if self.min_events <= 0:
            raise ValueError("min_events must be > 0")
        if self.max_events is not None and self.max_events <= 0:
            raise ValueError("max_events must be > 0 when provided")
        if self.max_events is not None and self.max_events < self.min_events:
            raise ValueError("max_events must be >= min_events")

    def resolve(self, context: HorizonContext) -> HorizonSpec:
        if not context.past_values:
            raise ValueError("past_values are required to estimate half-life")
        half_life = self.estimator(context.past_values)
        if half_life <= 0:
            raise ValueError("estimated half-life must be positive")
        raw_events = math.ceil(half_life * self.multiplier)
        event_count = max(self.min_events, raw_events)
        if self.max_events is not None:
            event_count = min(event_count, self.max_events)
        if context.event_timedelta is not None:
            return HorizonSpec(
                max_duration=context.event_timedelta * event_count,
                frozen_at=context.entry_time,
            )
        return HorizonSpec(
            max_bars=event_count,
            frozen_at=context.entry_time,
        )


class CompositeHorizonMode(str, Enum):
    """Strategies for combining multiple horizon resolvers."""

    MIN = "min"
    FIRST_EXPIRY = "first_expiry"
    PRIORITY = "priority"


@dataclass(frozen=True)
class CompositeHorizonResolver:
    """Combine multiple resolvers into a single horizon decision."""

    resolvers: Sequence[HorizonResolver]
    mode: CompositeHorizonMode = CompositeHorizonMode.MIN

    def __post_init__(self) -> None:
        if not self.resolvers:
            raise ValueError("resolvers must not be empty")

    def resolve(self, context: HorizonContext) -> HorizonSpec:
        specs = [resolver.resolve(context) for resolver in self.resolvers]
        if self.mode == CompositeHorizonMode.PRIORITY:
            for spec in specs:
                if spec.max_duration is not None or spec.max_bars is not None:
                    return _freeze_spec(spec, context.entry_time)
            return HorizonSpec(frozen_at=context.entry_time)
        return _merge_min_specs(specs, context.entry_time)


def _freeze_spec(spec: HorizonSpec, entry_time: datetime) -> HorizonSpec:
    if spec.frozen_at and spec.frozen_at != entry_time:
        raise ValueError("horizon.frozen_at must match entry_time")
    return HorizonSpec(
        max_duration=spec.max_duration,
        max_bars=spec.max_bars,
        frozen_at=entry_time,
    )


def _merge_min_specs(specs: Iterable[HorizonSpec], entry_time: datetime) -> HorizonSpec:
    durations = [spec.max_duration for spec in specs if spec.max_duration is not None]
    bars = [spec.max_bars for spec in specs if spec.max_bars is not None]
    min_duration = min(durations) if durations else None
    min_bars = min(bars) if bars else None
    return HorizonSpec(
        max_duration=min_duration,
        max_bars=min_bars,
        frozen_at=entry_time,
    )


__all__ = [
    "CompositeHorizonMode",
    "CompositeHorizonResolver",
    "EventCountHorizonResolver",
    "HalfLifeHorizonResolver",
    "HorizonContext",
    "HorizonResolver",
    "estimate_half_life",
]
