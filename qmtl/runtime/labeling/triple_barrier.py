"""Triple-barrier state machine for delayed-label emission."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from itertools import count
from typing import Callable, Mapping

from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec, HorizonSpec, LabelOutcome


_SIDE_ALIASES = {
    "long": "long",
    "short": "short",
    "buy": "long",
    "sell": "short",
}


def _normalize_side(side: str) -> str:
    if not side:
        raise ValueError("side is required")
    normalized = _SIDE_ALIASES.get(side.lower())
    if normalized is None:
        raise ValueError(f"side must be one of {sorted(_SIDE_ALIASES)}")
    return normalized


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _validate_specs(
    entry_time: datetime,
    barrier: BarrierSpec,
    horizon: HorizonSpec,
) -> None:
    if barrier.frozen_at and barrier.frozen_at != entry_time:
        raise ValueError("barrier.frozen_at must match entry_time when set")
    if horizon.frozen_at and horizon.frozen_at != entry_time:
        raise ValueError("horizon.frozen_at must match entry_time when set")
    if horizon.max_bars is not None and horizon.max_bars <= 0:
        raise ValueError("horizon.max_bars must be > 0 when provided")
    if horizon.max_duration is not None and horizon.max_duration <= timedelta(0):
        raise ValueError("horizon.max_duration must be > 0 when provided")


@dataclass(frozen=True)
class TripleBarrierEntry:
    """Entry event for a triple-barrier labeling workflow."""

    entry_time: datetime
    entry_price: float
    side: str
    entry_id: str | None = None
    symbol: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TripleBarrierObservation:
    """Observed price update after entry."""

    observed_time: datetime
    price: float
    symbol: str | None = None


@dataclass(frozen=True)
class TripleBarrierLabel:
    """Resolved label emitted once after a terminal barrier is hit."""

    entry_id: str
    entry_time: datetime
    resolved_time: datetime
    entry_price: float
    resolved_price: float
    side: str
    outcome: LabelOutcome
    barrier: BarrierSpec
    horizon: HorizonSpec
    realized_return: float
    pnl_gross: float
    pnl_net: float
    reason: str
    symbol: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.resolved_time <= self.entry_time:
            raise ValueError("resolved_time must be > entry_time")
        if self.barrier.frozen_at and self.barrier.frozen_at != self.entry_time:
            raise ValueError("barrier.frozen_at must match entry_time when set")
        if self.horizon.frozen_at and self.horizon.frozen_at != self.entry_time:
            raise ValueError("horizon.frozen_at must match entry_time when set")


@dataclass
class _EntryState:
    entry: TripleBarrierEntry
    barrier: BarrierSpec
    horizon: HorizonSpec
    bars_observed: int = 0


class TripleBarrierStateMachine:
    """Track entry events and emit labels when PT/SL/timeout is reached."""

    def __init__(
        self,
        *,
        cost_model: Callable[[TripleBarrierEntry, TripleBarrierObservation, float], float]
        | None = None,
    ) -> None:
        self._cost_model = cost_model
        self._entries: dict[str, _EntryState] = {}
        self._resolved: set[str] = set()
        self._sequence = count(1)

    def register_entry(
        self,
        entry: TripleBarrierEntry,
        barrier: BarrierSpec,
        horizon: HorizonSpec,
    ) -> str:
        """Register an entry event and return the entry_id used."""
        _validate_positive("entry_price", entry.entry_price)
        normalized_side = _normalize_side(entry.side)
        _validate_specs(entry.entry_time, barrier, horizon)
        entry_id = entry.entry_id or self._default_entry_id(entry)
        if entry_id in self._entries or entry_id in self._resolved:
            raise ValueError(f"entry_id {entry_id!r} is already registered")
        normalized_entry = replace(entry, side=normalized_side, entry_id=entry_id)
        self._entries[entry_id] = _EntryState(
            entry=normalized_entry,
            barrier=barrier,
            horizon=horizon,
        )
        return entry_id

    def update(self, observation: TripleBarrierObservation) -> list[TripleBarrierLabel]:
        """Consume a price observation and return any resolved labels."""
        labels: list[TripleBarrierLabel] = []
        for entry_id, state in list(self._entries.items()):
            if not _symbols_match(state.entry.symbol, observation.symbol):
                continue
            label = self._maybe_resolve(state, observation)
            if label is None:
                continue
            labels.append(label)
            del self._entries[entry_id]
            self._resolved.add(entry_id)
        return labels

    def _maybe_resolve(
        self,
        state: _EntryState,
        observation: TripleBarrierObservation,
    ) -> TripleBarrierLabel | None:
        entry = state.entry
        if observation.observed_time <= entry.entry_time:
            return None
        state.bars_observed += 1
        realized_return = _signed_return(entry.entry_price, observation.price, entry.side)
        outcome = _barrier_outcome(
            barrier=state.barrier,
            side=entry.side,
            entry_price=entry.entry_price,
            observed_price=observation.price,
            realized_return=realized_return,
        )
        if outcome is None and _is_timeout(state, observation.observed_time):
            outcome = LabelOutcome.TIMEOUT
        if outcome is None:
            return None
        pnl_gross = realized_return
        pnl_net = (
            self._cost_model(entry, observation, pnl_gross)
            if self._cost_model is not None
            else pnl_gross
        )
        return TripleBarrierLabel(
            entry_id=entry.entry_id or "",
            entry_time=entry.entry_time,
            resolved_time=observation.observed_time,
            entry_price=entry.entry_price,
            resolved_price=observation.price,
            side=entry.side,
            outcome=outcome,
            barrier=state.barrier,
            horizon=state.horizon,
            realized_return=realized_return,
            pnl_gross=pnl_gross,
            pnl_net=pnl_net,
            reason=outcome.value,
            symbol=entry.symbol,
            metadata=entry.metadata,
        )

    def _default_entry_id(self, entry: TripleBarrierEntry) -> str:
        sequence = next(self._sequence)
        symbol = entry.symbol or "entry"
        return f"{symbol}-{entry.entry_time.isoformat()}-{sequence}"


def _symbols_match(entry_symbol: str | None, observation_symbol: str | None) -> bool:
    if entry_symbol is None or observation_symbol is None:
        return True
    return entry_symbol == observation_symbol


def _signed_return(entry_price: float, observed_price: float, side: str) -> float:
    if side == "long":
        return (observed_price - entry_price) / entry_price
    return (entry_price - observed_price) / entry_price


def _barrier_outcome(
    *,
    barrier: BarrierSpec,
    side: str,
    entry_price: float,
    observed_price: float,
    realized_return: float,
) -> LabelOutcome | None:
    if barrier.mode == BarrierMode.PRICE:
        return _price_outcome(barrier, side, observed_price)
    if barrier.mode == BarrierMode.RETURN:
        return _return_outcome(barrier, realized_return)
    raise ValueError("unsupported barrier mode")


def _price_outcome(
    barrier: BarrierSpec,
    side: str,
    observed_price: float,
) -> LabelOutcome | None:
    profit_target = barrier.profit_target
    stop_loss = barrier.stop_loss
    if side == "long":
        if profit_target is not None and observed_price >= profit_target:
            return LabelOutcome.PROFIT_TARGET
        if stop_loss is not None and observed_price <= stop_loss:
            return LabelOutcome.STOP_LOSS
        return None
    if profit_target is not None and observed_price <= profit_target:
        return LabelOutcome.PROFIT_TARGET
    if stop_loss is not None and observed_price >= stop_loss:
        return LabelOutcome.STOP_LOSS
    return None


def _return_outcome(
    barrier: BarrierSpec,
    realized_return: float,
) -> LabelOutcome | None:
    profit_target = barrier.profit_target
    stop_loss = barrier.stop_loss
    if profit_target is not None and realized_return >= profit_target:
        return LabelOutcome.PROFIT_TARGET
    if stop_loss is not None and realized_return <= -stop_loss:
        return LabelOutcome.STOP_LOSS
    return None


def _is_timeout(state: _EntryState, observed_time: datetime) -> bool:
    horizon = state.horizon
    entry_time = state.entry.entry_time
    if horizon.max_duration is not None:
        if observed_time >= entry_time + horizon.max_duration:
            return True
    if horizon.max_bars is not None:
        if state.bars_observed >= horizon.max_bars:
            return True
    return False


__all__ = [
    "TripleBarrierEntry",
    "TripleBarrierLabel",
    "TripleBarrierObservation",
    "TripleBarrierStateMachine",
]
