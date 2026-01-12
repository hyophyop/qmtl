"""Utilities for meta-labeling with triple-barrier outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from qmtl.runtime.labeling.schema import LabelOutcome
from qmtl.runtime.labeling.triple_barrier import TripleBarrierLabel

_SIDE_ALIASES = {
    "long": "long",
    "short": "short",
    "buy": "long",
    "sell": "short",
}


@dataclass(frozen=True)
class MetaLabel:
    """Meta-label output for entry decision modeling."""

    meta_label: int
    side: str
    entry_decision: int | None
    outcome: LabelOutcome
    barrier_hit: str
    reason: str


def meta_label_from_outcome(
    *,
    side: str,
    outcome: LabelOutcome,
    entry_decision: int | None = None,
) -> MetaLabel:
    """Convert a triple-barrier outcome into a meta-label decision."""
    normalized_side = _normalize_side(side)
    normalized_entry = _normalize_entry_decision(entry_decision)
    base_label = 1 if outcome == LabelOutcome.PROFIT_TARGET else 0
    if normalized_entry == 0:
        return MetaLabel(
            meta_label=0,
            side=normalized_side,
            entry_decision=normalized_entry,
            outcome=outcome,
            barrier_hit=outcome.value,
            reason="entry_filtered",
        )
    return MetaLabel(
        meta_label=base_label,
        side=normalized_side,
        entry_decision=normalized_entry,
        outcome=outcome,
        barrier_hit=outcome.value,
        reason=outcome.value,
    )


def meta_label_from_triple_barrier(
    label: TripleBarrierLabel,
    *,
    side_signal: str | None = None,
    entry_decision: int | None = None,
) -> MetaLabel:
    """Create a meta-label from a triple-barrier label and optional entry decision."""
    resolved_side = side_signal or label.side
    normalized_side = _normalize_side(resolved_side)
    if side_signal is not None and normalized_side != label.side:
        raise ValueError("side_signal must match label.side")
    return meta_label_from_outcome(
        side=normalized_side,
        outcome=label.outcome,
        entry_decision=entry_decision,
    )


def _normalize_side(side: str) -> str:
    if not side:
        raise ValueError("side is required")
    normalized = _SIDE_ALIASES.get(side.lower())
    if normalized is None:
        raise ValueError(f"side must be one of {sorted(_SIDE_ALIASES)}")
    return normalized


def _normalize_entry_decision(entry_decision: int | None) -> int | None:
    if entry_decision is None:
        return None
    if entry_decision not in (0, 1):
        raise ValueError("entry_decision must be 0 or 1 when provided")
    return entry_decision


__all__ = [
    "MetaLabel",
    "meta_label_from_outcome",
    "meta_label_from_triple_barrier",
]
