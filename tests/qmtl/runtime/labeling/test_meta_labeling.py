from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from qmtl.runtime.labeling.meta import (
    MetaLabel,
    meta_label_from_outcome,
    meta_label_from_triple_barrier,
)
from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec, HorizonSpec, LabelOutcome
from qmtl.runtime.labeling.triple_barrier import TripleBarrierLabel


def test_meta_label_from_outcome_profit_target() -> None:
    label = meta_label_from_outcome(side="long", outcome=LabelOutcome.PROFIT_TARGET)
    assert label == MetaLabel(
        meta_label=1,
        side="long",
        entry_decision=None,
        outcome=LabelOutcome.PROFIT_TARGET,
        barrier_hit="profit_target",
        reason="profit_target",
    )


def test_meta_label_from_outcome_entry_filtered() -> None:
    label = meta_label_from_outcome(
        side="short",
        outcome=LabelOutcome.STOP_LOSS,
        entry_decision=0,
    )
    assert label.meta_label == 0
    assert label.reason == "entry_filtered"
    assert label.entry_decision == 0


def test_meta_label_from_outcome_validates_inputs() -> None:
    with pytest.raises(ValueError, match="side is required"):
        meta_label_from_outcome(side="", outcome=LabelOutcome.TIMEOUT)
    with pytest.raises(ValueError, match="entry_decision must be 0 or 1"):
        meta_label_from_outcome(
            side="long",
            outcome=LabelOutcome.TIMEOUT,
            entry_decision=2,
        )


def test_meta_label_from_triple_barrier_side_validation() -> None:
    entry_time = datetime(2025, 1, 1, 9, 30)
    label = TripleBarrierLabel(
        entry_id="entry-1",
        entry_time=entry_time,
        resolved_time=entry_time + timedelta(minutes=1),
        entry_price=100.0,
        resolved_price=110.0,
        side="long",
        outcome=LabelOutcome.PROFIT_TARGET,
        barrier=BarrierSpec(
            profit_target=0.1,
            stop_loss=0.05,
            mode=BarrierMode.RETURN,
            frozen_at=entry_time,
        ),
        horizon=HorizonSpec(max_bars=1, frozen_at=entry_time),
        realized_return=0.1,
        pnl_gross=0.1,
        pnl_net=0.1,
        reason="profit_target",
    )

    meta = meta_label_from_triple_barrier(label)
    assert meta.meta_label == 1
    assert meta.side == "long"

    with pytest.raises(ValueError, match="side_signal must match label.side"):
        meta_label_from_triple_barrier(label, side_signal="short")
