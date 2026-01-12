from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from qmtl.runtime.labeling.costs import FixedBpsCostModel
from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec, HorizonSpec, LabelOutcome
from qmtl.runtime.labeling.triple_barrier import (
    TripleBarrierEntry,
    TripleBarrierObservation,
    TripleBarrierStateMachine,
)


def test_triple_barrier_delayed_emit_and_idempotent() -> None:
    entry_time = datetime(2025, 1, 1, 9, 30)
    barrier = BarrierSpec(
        profit_target=110.0,
        stop_loss=90.0,
        mode=BarrierMode.PRICE,
        frozen_at=entry_time,
    )
    horizon = HorizonSpec(max_bars=3, frozen_at=entry_time)
    machine = TripleBarrierStateMachine()
    entry = TripleBarrierEntry(
        entry_time=entry_time,
        entry_price=100.0,
        side="long",
        entry_id="entry-1",
    )
    machine.register_entry(entry, barrier, horizon)

    same_time = TripleBarrierObservation(observed_time=entry_time, price=110.0)
    assert machine.update(same_time) == []

    first_tick = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=1),
        price=105.0,
    )
    assert machine.update(first_tick) == []

    hit_target = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=2),
        price=111.0,
    )
    labels = machine.update(hit_target)
    assert len(labels) == 1
    label = labels[0]
    assert label.entry_id == "entry-1"
    assert label.resolved_time == hit_target.observed_time
    assert label.outcome == LabelOutcome.PROFIT_TARGET

    later_tick = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=3),
        price=120.0,
    )
    assert machine.update(later_tick) == []


def test_triple_barrier_timeout() -> None:
    entry_time = datetime(2025, 1, 1, 9, 30)
    barrier = BarrierSpec(
        profit_target=None,
        stop_loss=None,
        mode=BarrierMode.PRICE,
        frozen_at=entry_time,
    )
    horizon = HorizonSpec(max_bars=2, frozen_at=entry_time)
    machine = TripleBarrierStateMachine()
    entry = TripleBarrierEntry(
        entry_time=entry_time,
        entry_price=100.0,
        side="short",
        entry_id="entry-2",
    )
    machine.register_entry(entry, barrier, horizon)

    first_tick = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=1),
        price=101.0,
    )
    assert machine.update(first_tick) == []

    second_tick = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=2),
        price=102.0,
    )
    labels = machine.update(second_tick)
    assert len(labels) == 1
    label = labels[0]
    assert label.entry_id == "entry-2"
    assert label.outcome == LabelOutcome.TIMEOUT


def test_triple_barrier_net_outcome_with_costs() -> None:
    entry_time = datetime(2025, 1, 1, 9, 30)
    barrier = BarrierSpec(
        profit_target=0.02,
        stop_loss=0.02,
        mode=BarrierMode.RETURN,
        frozen_at=entry_time,
    )
    horizon = HorizonSpec(max_bars=3, frozen_at=entry_time)
    cost_model = FixedBpsCostModel(total_cost_bps=50.0, min_edge_bps=20.0)
    machine = TripleBarrierStateMachine(cost_model=cost_model)
    entry = TripleBarrierEntry(
        entry_time=entry_time,
        entry_price=100.0,
        side="long",
        entry_id="entry-3",
    )
    machine.register_entry(entry, barrier, horizon)

    gross_hit = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=1),
        price=102.0,
    )
    assert machine.update(gross_hit) == []

    net_hit = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=2),
        price=103.0,
    )
    labels = machine.update(net_hit)
    assert len(labels) == 1
    label = labels[0]
    assert label.outcome == LabelOutcome.PROFIT_TARGET
    assert label.outcome_gross == LabelOutcome.PROFIT_TARGET
    assert label.pnl_gross == pytest.approx(0.03)
    assert label.pnl_net == pytest.approx(0.023)
    assert label.net_only_stop is False


def test_triple_barrier_net_only_stop_preserves_gross_none() -> None:
    entry_time = datetime(2025, 1, 1, 9, 30)
    barrier = BarrierSpec(
        profit_target=0.03,
        stop_loss=0.02,
        mode=BarrierMode.RETURN,
        frozen_at=entry_time,
    )
    horizon = HorizonSpec(max_bars=2, frozen_at=entry_time)
    cost_model = FixedBpsCostModel(total_cost_bps=100.0, min_edge_bps=0.0)
    machine = TripleBarrierStateMachine(cost_model=cost_model)
    entry = TripleBarrierEntry(
        entry_time=entry_time,
        entry_price=100.0,
        side="long",
        entry_id="entry-4",
    )
    machine.register_entry(entry, barrier, horizon)

    net_only_stop = TripleBarrierObservation(
        observed_time=entry_time + timedelta(minutes=1),
        price=98.5,
    )
    labels = machine.update(net_only_stop)
    assert len(labels) == 1
    label = labels[0]
    assert label.outcome == LabelOutcome.STOP_LOSS
    assert label.outcome_gross is None
    assert label.net_only_stop is True
