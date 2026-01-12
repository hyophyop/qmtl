"""Labeling schema and guardrail contracts."""

from qmtl.runtime.labeling.barriers import volatility_scaled_barrier_spec
from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec, HorizonSpec, LabelEvent, LabelOutcome

__all__ = [
    "BarrierSpec",
    "BarrierMode",
    "HorizonSpec",
    "LabelEvent",
    "LabelOutcome",
    "volatility_scaled_barrier_spec",
]
