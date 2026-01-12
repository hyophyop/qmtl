from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from qmtl.runtime.labeling.time_barrier import (
    CompositeHorizonMode,
    CompositeHorizonResolver,
    EventCountHorizonResolver,
    HalfLifeHorizonResolver,
    HorizonContext,
    estimate_half_life,
)


def test_estimate_half_life_from_mean_reverting_series() -> None:
    values = [1.0, 0.5, 0.25, 0.125, 0.0625]

    half_life = estimate_half_life(values)

    assert half_life == pytest.approx(1.0)


def test_estimate_half_life_rejects_flat_series() -> None:
    with pytest.raises(ValueError, match="non-zero variance"):
        estimate_half_life([1.0, 1.0, 1.0])


def test_event_count_horizon_resolver_freezes_entry_time() -> None:
    entry_time = datetime(2025, 1, 1)
    context = HorizonContext(entry_time=entry_time)
    resolver = EventCountHorizonResolver(max_events=12)

    spec = resolver.resolve(context)

    assert spec.max_bars == 12
    assert spec.max_duration is None
    assert spec.frozen_at == entry_time


def test_half_life_horizon_resolver_uses_event_counts() -> None:
    entry_time = datetime(2025, 1, 1)
    context = HorizonContext(
        entry_time=entry_time,
        past_values=[1.0, 0.5, 0.25, 0.125, 0.0625],
    )
    resolver = HalfLifeHorizonResolver(multiplier=3.0, min_events=2)

    spec = resolver.resolve(context)

    assert spec.max_bars == 3
    assert spec.max_duration is None
    assert spec.frozen_at == entry_time


def test_half_life_horizon_resolver_can_return_duration() -> None:
    entry_time = datetime(2025, 1, 1)
    context = HorizonContext(
        entry_time=entry_time,
        past_values=[1.0, 0.5, 0.25, 0.125, 0.0625],
        event_timedelta=timedelta(minutes=5),
    )
    resolver = HalfLifeHorizonResolver(multiplier=2.0)

    spec = resolver.resolve(context)

    assert spec.max_bars is None
    assert spec.max_duration == timedelta(minutes=10)
    assert spec.frozen_at == entry_time


def test_composite_horizon_min_uses_smallest_limits() -> None:
    entry_time = datetime(2025, 1, 1)
    context = HorizonContext(
        entry_time=entry_time,
        past_values=[1.0, 0.5, 0.25, 0.125, 0.0625],
    )
    composite = CompositeHorizonResolver(
        resolvers=[
            EventCountHorizonResolver(max_events=10),
            HalfLifeHorizonResolver(multiplier=2.0),
        ],
        mode=CompositeHorizonMode.MIN,
    )

    spec = composite.resolve(context)

    assert spec.max_bars == 2
    assert spec.frozen_at == entry_time


def test_composite_horizon_priority_uses_first_resolver() -> None:
    entry_time = datetime(2025, 1, 1)
    context = HorizonContext(
        entry_time=entry_time,
        past_values=[1.0, 0.5, 0.25, 0.125, 0.0625],
    )
    composite = CompositeHorizonResolver(
        resolvers=[
            EventCountHorizonResolver(max_events=10),
            HalfLifeHorizonResolver(multiplier=2.0),
        ],
        mode=CompositeHorizonMode.PRIORITY,
    )

    spec = composite.resolve(context)

    assert spec.max_bars == 10
    assert spec.frozen_at == entry_time
