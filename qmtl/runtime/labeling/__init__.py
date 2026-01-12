"""Labeling schema and guardrail contracts."""

from qmtl.runtime.labeling.barriers import volatility_scaled_barrier_spec
from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec, HorizonSpec, LabelEvent, LabelOutcome
from qmtl.runtime.labeling.time_barrier import (
    CompositeHorizonMode,
    CompositeHorizonResolver,
    EventCountHorizonResolver,
    HalfLifeHorizonResolver,
    HorizonContext,
    HorizonResolver,
    estimate_half_life,
)
from qmtl.runtime.labeling.triple_barrier import (
    TripleBarrierEntry,
    TripleBarrierLabel,
    TripleBarrierObservation,
    TripleBarrierStateMachine,
)

__all__ = [
    "BarrierSpec",
    "BarrierMode",
    "HorizonSpec",
    "LabelEvent",
    "LabelOutcome",
    "volatility_scaled_barrier_spec",
    "CompositeHorizonMode",
    "CompositeHorizonResolver",
    "EventCountHorizonResolver",
    "HalfLifeHorizonResolver",
    "HorizonContext",
    "HorizonResolver",
    "estimate_half_life",
    "TripleBarrierEntry",
    "TripleBarrierLabel",
    "TripleBarrierObservation",
    "TripleBarrierStateMachine",
]
