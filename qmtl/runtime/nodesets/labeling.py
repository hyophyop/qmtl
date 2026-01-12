from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping

from qmtl.runtime.labeling.costs import CostModel
from qmtl.runtime.labeling.schema import BarrierMode, BarrierSpec, HorizonSpec
from qmtl.runtime.labeling.triple_barrier import (
    TripleBarrierEntry,
    TripleBarrierLabel,
    TripleBarrierObservation,
    TripleBarrierStateMachine,
)
from qmtl.runtime.sdk import CacheView, Node


def build_triple_barrier_label_node(
    price_node: Node,
    entry_node: Node,
    *,
    default_barrier: BarrierSpec | Mapping[str, Any] | None = None,
    default_horizon: HorizonSpec | Mapping[str, Any] | None = None,
    cost_model: CostModel | None = None,
    name: str | None = None,
) -> Node:
    """Return a labeling node that emits delayed triple-barrier labels."""

    if price_node.node_id == entry_node.node_id:
        raise ValueError("price_node and entry_node must be distinct nodes")

    state = TripleBarrierStateMachine(cost_model=cost_model)
    last_entry_event_id: int | None = None
    last_entry_event_count = 0
    last_price_event_id: int | None = None
    last_price_event_count = 0

    def _compute(view: CacheView) -> list[TripleBarrierLabel] | None:
        nonlocal last_entry_event_id
        nonlocal last_entry_event_count
        nonlocal last_price_event_id
        nonlocal last_price_event_count

        entry_events = _latest_events(view, entry_node)
        new_entry_events, (entry_updated, entry_count) = _select_new_events(
            entry_events,
            last_entry_event_id,
            last_entry_event_count,
        )
        for _, payload in new_entry_events:
            entry, barrier, horizon = _coerce_entry_payload(
                payload,
                default_barrier=default_barrier,
                default_horizon=default_horizon,
            )
            state.register_entry(entry, barrier, horizon)
        last_entry_event_id = entry_updated
        last_entry_event_count = entry_count

        price_events = _latest_events(view, price_node)
        new_price_events, (price_updated, price_count) = _select_new_events(
            price_events,
            last_price_event_id,
            last_price_event_count,
        )
        labels: list[TripleBarrierLabel] = []
        for _, payload in new_price_events:
            if not _is_observation_payload(payload):
                continue
            observation = _coerce_observation_payload(payload)
            labels.extend(state.update(observation))
        last_price_event_id = price_updated
        last_price_event_count = price_count
        if not labels:
            return None
        return labels

    interval = price_node.interval or entry_node.interval
    if interval is None:
        raise ValueError("price_node or entry_node must define an interval")
    period = max(1, entry_node.period or 1, price_node.period or 1)
    return Node(
        input=(entry_node, price_node),
        compute_fn=_compute,
        name=name or "triple_barrier_labeler",
        interval=interval,
        period=period,
    )


def _latest_events(view: CacheView, node: Node) -> list[tuple[int, Any]]:
    if node.interval is None:
        raise ValueError(f"{node.name} must define an interval")
    try:
        return list(view[node][node.interval])
    except KeyError:
        return []


def _select_new_events(
    events: list[tuple[int, Any]],
    last_event_id: int | None,
    last_event_count: int,
) -> tuple[list[tuple[int, Any]], tuple[int | None, int]]:
    if not events:
        return [], (last_event_id, last_event_count)
    if last_event_id is None:
        return events, _event_cursor(events, last_event_id, last_event_count)

    new_events: list[tuple[int, Any]] = []
    seen_last = 0
    for event_id, payload in events:
        if event_id < last_event_id:
            continue
        if event_id == last_event_id:
            seen_last += 1
            if seen_last <= last_event_count:
                continue
        new_events.append((event_id, payload))
    return new_events, _event_cursor(events, last_event_id, last_event_count)


def _event_cursor(
    events: list[tuple[int, Any]],
    last_event_id: int | None,
    last_event_count: int,
) -> tuple[int | None, int]:
    if not events:
        return last_event_id, last_event_count
    latest_id = events[-1][0]
    latest_count = sum(1 for event_id, _ in events if event_id == latest_id)
    if last_event_id is None:
        return latest_id, latest_count
    if latest_id > last_event_id or (
        latest_id == last_event_id and latest_count > last_event_count
    ):
        return latest_id, latest_count
    return last_event_id, last_event_count


def _coerce_entry_payload(
    payload: TripleBarrierEntry | Mapping[str, Any],
    *,
    default_barrier: BarrierSpec | Mapping[str, Any] | None,
    default_horizon: HorizonSpec | Mapping[str, Any] | None,
) -> tuple[TripleBarrierEntry, BarrierSpec, HorizonSpec]:
    if isinstance(payload, TripleBarrierEntry):
        entry = payload
        barrier_value = default_barrier
        horizon_value = default_horizon
    elif isinstance(payload, Mapping):
        entry_time = _require_datetime(payload.get("entry_time"), "entry_time")
        entry_price = _require_float(payload.get("entry_price"), "entry_price")
        side = _require_str(payload.get("side"), "side")
        entry = TripleBarrierEntry(
            entry_time=entry_time,
            entry_price=entry_price,
            side=side,
            entry_id=payload.get("entry_id"),
            symbol=payload.get("symbol"),
            metadata=dict(payload.get("metadata") or {}),
        )
        barrier_value = payload.get("barrier", default_barrier)
        horizon_value = payload.get("horizon", default_horizon)
    else:
        raise TypeError("entry payload must be a TripleBarrierEntry or mapping")

    if barrier_value is None:
        raise ValueError("barrier specification is required for triple-barrier labeling")
    if horizon_value is None:
        raise ValueError("horizon specification is required for triple-barrier labeling")

    barrier = _coerce_barrier_spec(barrier_value, entry.entry_time)
    horizon = _coerce_horizon_spec(horizon_value, entry.entry_time)
    return entry, barrier, horizon


def _coerce_observation_payload(
    payload: TripleBarrierObservation | Mapping[str, Any],
) -> TripleBarrierObservation:
    if isinstance(payload, TripleBarrierObservation):
        return payload
    if not isinstance(payload, Mapping):
        raise TypeError("observation payload must be a TripleBarrierObservation or mapping")
    observed_time = _require_datetime(payload.get("observed_time"), "observed_time")
    price = _require_float(payload.get("price"), "price")
    return TripleBarrierObservation(
        observed_time=observed_time,
        price=price,
        symbol=payload.get("symbol"),
    )


def _is_observation_payload(payload: Any) -> bool:
    if isinstance(payload, TripleBarrierObservation):
        return True
    if isinstance(payload, Mapping):
        return "observed_time" in payload and "price" in payload
    return False


def _coerce_barrier_spec(
    value: BarrierSpec | Mapping[str, Any],
    entry_time: datetime,
) -> BarrierSpec:
    if isinstance(value, BarrierSpec):
        return _freeze_barrier_spec(value, entry_time)
    if not isinstance(value, Mapping):
        raise TypeError("barrier must be a BarrierSpec or mapping")
    mode = value.get("mode", BarrierMode.RETURN)
    if isinstance(mode, str):
        mode = BarrierMode(mode)
    return _freeze_barrier_spec(
        BarrierSpec(
            profit_target=value.get("profit_target"),
            stop_loss=value.get("stop_loss"),
            mode=mode,
            frozen_at=value.get("frozen_at"),
        ),
        entry_time,
    )


def _coerce_horizon_spec(
    value: HorizonSpec | Mapping[str, Any],
    entry_time: datetime,
) -> HorizonSpec:
    if isinstance(value, HorizonSpec):
        return _freeze_horizon_spec(value, entry_time)
    if not isinstance(value, Mapping):
        raise TypeError("horizon must be a HorizonSpec or mapping")
    return _freeze_horizon_spec(
        HorizonSpec(
            max_duration=value.get("max_duration"),
            max_bars=value.get("max_bars"),
            frozen_at=value.get("frozen_at"),
        ),
        entry_time,
    )


def _freeze_barrier_spec(barrier: BarrierSpec, entry_time: datetime) -> BarrierSpec:
    if barrier.frozen_at and barrier.frozen_at != entry_time:
        raise ValueError("barrier.frozen_at must match entry_time when set")
    return replace(barrier, frozen_at=entry_time)


def _freeze_horizon_spec(horizon: HorizonSpec, entry_time: datetime) -> HorizonSpec:
    if horizon.frozen_at and horizon.frozen_at != entry_time:
        raise ValueError("horizon.frozen_at must match entry_time when set")
    return replace(horizon, frozen_at=entry_time)


def _require_datetime(value: Any, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    return value


def _require_float(value: Any, name: str) -> float:
    if value is None:
        raise ValueError(f"{name} is required")
    return float(value)


def _require_str(value: Any, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


__all__ = ["build_triple_barrier_label_node"]
