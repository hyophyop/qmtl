from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from .cache_view_tools import _as_sequence
from .protocols import NodeLike
from .util import parse_interval

Duration = int | float | str | None
TemporalKind = Literal["bar", "event", "state"]
JoinMode = Literal["exact", "asof", "interval", "temporal"]
TriggerKind = Literal["source", "clock", "bar_close", "session_open"]
LatePolicy = Literal["drop", "side_output", "recompute"]

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(ms|s|m|h|d)?\s*$")
_DURATION_FACTORS = {
    None: 1000,
    "ms": 1,
    "s": 1000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
}
_VALID_TEMPORAL_KINDS = {"bar", "event", "state"}
_VALID_JOIN_MODES = {"exact", "asof", "interval", "temporal"}
_VALID_TRIGGER_KINDS = {"source", "clock", "bar_close", "session_open"}
_VALID_LATE_POLICIES = {"drop", "side_output", "recompute"}
_BAD_QUALITY_VALUES = {"bad", "gap", "sequence_gap", "stale", "invalid"}

__all__ = [
    "AlignedPayload",
    "AlignedView",
    "AlignmentInputSpec",
    "AlignmentInputStatus",
    "AlignmentStatus",
    "CalendarSpec",
    "JoinSpec",
    "TemporalAlignedOutputSpec",
    "TemporalSpec",
    "TriggerSpec",
    "WatermarkPolicy",
    "align_temporal",
    "alignment_to_config",
    "build_node_output",
    "duration_to_ms",
    "infer_join_specs",
    "node_has_generated_output",
    "node_output_should_process",
    "output_to_config",
    "temporal_to_config",
    "validate_node_output_spec",
]


@dataclass(frozen=True)
class TemporalSpec:
    """Event-time metadata for a cache-backed stream."""

    kind: TemporalKind = "bar"
    event_ts: str = "event_ts"
    source_ts: str | None = None
    received_ts: str | None = "received_ts"
    timezone: str = "UTC"
    max_out_of_order: Duration = 0
    idle_after: Duration = None
    sequence: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _VALID_TEMPORAL_KINDS:
            raise ValueError(f"unsupported temporal kind: {self.kind!r}")

    @property
    def max_out_of_order_ms(self) -> int:
        return duration_to_ms(self.max_out_of_order, default=0) or 0

    @property
    def idle_after_ms(self) -> int | None:
        return duration_to_ms(self.idle_after)

    def as_config(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "event_ts": self.event_ts,
            "source_ts": self.source_ts,
            "received_ts": self.received_ts,
            "timezone": self.timezone,
            "max_out_of_order": self.max_out_of_order,
            "idle_after": self.idle_after,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class CalendarSpec:
    """Adapter hook for exchange/session-aware temporal alignment."""

    name: str
    timezone: str = "UTC"
    session_field: str = "session_state"


@dataclass(frozen=True)
class TriggerSpec:
    """Describe the event source that defines an alignment timestamp."""

    kind: TriggerKind = "source"
    source: NodeLike | str | None = None
    calendar: CalendarSpec | None = None

    def __post_init__(self) -> None:
        if self.kind not in _VALID_TRIGGER_KINDS:
            raise ValueError(f"unsupported trigger kind: {self.kind!r}")


@dataclass(frozen=True)
class AlignmentInputSpec:
    """Per-source defaults used when a consumer auto-builds temporal joins."""

    alias: str | None = None
    partition_key: str | None = None
    mode: JoinMode | None = None
    tolerance: Duration = None
    max_age: Duration = None
    required: bool | None = None
    closed_only: bool | None = None
    partition_value: Any | None = None
    calendar: CalendarSpec | None = None

    def __post_init__(self) -> None:
        if self.mode is not None and self.mode not in _VALID_JOIN_MODES:
            raise ValueError(f"unsupported join mode: {self.mode!r}")
        if self.alias is not None and not str(self.alias).strip():
            raise ValueError("alignment alias must not be empty")

    def as_config(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "partition_key": self.partition_key,
            "mode": self.mode,
            "tolerance": self.tolerance,
            "max_age": self.max_age,
            "required": self.required,
            "closed_only": self.closed_only,
            "partition_value": self.partition_value,
            "calendar": self.calendar.name if self.calendar else None,
        }


@dataclass(frozen=True)
class JoinSpec:
    """Temporal lookup policy for one aligned input."""

    node: NodeLike | str
    interval: int | None = None
    mode: JoinMode = "asof"
    tolerance: Duration = None
    max_age: Duration = None
    required: bool = True
    closed_only: bool = True
    partition_key: str | None = None
    partition_value: Any | None = None
    temporal: TemporalSpec | None = None
    calendar: CalendarSpec | None = None

    def __post_init__(self) -> None:
        if self.mode not in _VALID_JOIN_MODES:
            raise ValueError(f"unsupported join mode: {self.mode!r}")

    @classmethod
    def infer(
        cls,
        name: str,
        node: Any,
        *,
        trigger: Any | None = None,
        partition_key: str | None = None,
        override: Mapping[str, Any] | None = None,
    ) -> "JoinSpec":
        """Infer a join policy from node temporal metadata.

        Explicit :class:`JoinSpec` values remain the low-level escape hatch.
        Bare nodes must carry ``temporal`` metadata so inference cannot silently
        choose unsafe defaults.
        """

        if isinstance(node, JoinSpec):
            return _apply_join_overrides(node, override)
        if trigger is None:
            raise ValueError(f"trigger is required to infer JoinSpec for input {name!r}")

        candidate = _require_node_like(node, role=f"input {name!r}")
        alignment_data = _alignment_join_data(candidate)
        override_data = {**alignment_data, **_join_override_data(override)}
        temporal = _temporal_for_inference(name, candidate, override_data)
        interval = _interval_for_inference(name, candidate, override_data)
        trigger_input = _same_node_interval(candidate, trigger)
        effective_partition_key = (
            partition_key if partition_key is not None else override_data.get("partition_key")
        )
        data = _inferred_join_data(
            node=candidate,
            interval=interval,
            temporal=temporal,
            trigger_input=trigger_input,
            partition_key=effective_partition_key,
        )
        data.update(override_data)
        spec = cls(**data)
        _validate_inferred_join_spec(name, spec, trigger_input=trigger_input)
        return spec

    @property
    def node_id(self) -> str:
        return self.node.node_id if hasattr(self.node, "node_id") else str(self.node)

    @property
    def interval_value(self) -> int:
        interval = self.interval if self.interval is not None else getattr(self.node, "interval", None)
        if interval is None:
            raise ValueError(f"interval is required for JoinSpec[{self.node_id!r}]")
        return int(interval)

    @property
    def tolerance_ms(self) -> int | None:
        return duration_to_ms(self.tolerance)

    @property
    def max_age_ms(self) -> int | None:
        return duration_to_ms(self.max_age)

    def as_config(self) -> dict[str, Any]:
        return {
            "node": self.node_id,
            "interval": self.interval,
            "mode": self.mode,
            "tolerance": self.tolerance,
            "max_age": self.max_age,
            "required": self.required,
            "closed_only": self.closed_only,
            "partition_key": self.partition_key,
            "partition_value": self.partition_value,
            "temporal": self.temporal.as_config() if self.temporal else None,
            "calendar": self.calendar.name if self.calendar else None,
        }


@dataclass(frozen=True)
class WatermarkPolicy:
    """Readiness policy for late data and fast/slow source drift."""

    mode: str = "min_required"
    max_drift: Duration = None
    late: LatePolicy = "side_output"

    def __post_init__(self) -> None:
        if self.late not in _VALID_LATE_POLICIES:
            raise ValueError(f"unsupported late policy: {self.late!r}")

    @property
    def max_drift_ms(self) -> int | None:
        return duration_to_ms(self.max_drift)

    @classmethod
    def for_execution_domain(
        cls,
        execution_domain: str,
        *,
        mode: str = "min_required",
        max_drift: Duration = None,
        late: LatePolicy | None = None,
    ) -> "WatermarkPolicy":
        if late is None:
            late = "recompute" if execution_domain in {"backtest", "simulate"} else "side_output"
        return cls(mode=mode, max_drift=max_drift, late=late)


@dataclass(frozen=True)
class AlignmentInputStatus:
    name: str
    ready: bool
    reason: str | None
    required: bool = True
    selected_ts: int | None = None
    age_ms: int | None = None
    stale: bool = False
    missing: bool = False
    late: bool = False
    quality: str | None = None


@dataclass(frozen=True)
class AlignmentStatus:
    ready: bool
    trigger_ts: int
    reason: str | None = None
    missing_inputs: tuple[str, ...] = ()
    stale_inputs: tuple[str, ...] = ()
    late_inputs: tuple[str, ...] = ()
    quality_inputs: Mapping[str, str] = field(default_factory=dict)
    selected_ts: Mapping[str, int | None] = field(default_factory=dict)
    age_ms: Mapping[str, int | None] = field(default_factory=dict)
    inputs: Mapping[str, AlignmentInputStatus] = field(default_factory=dict)


@dataclass(frozen=True)
class AlignedView(Mapping[str, Any]):
    """Read-only temporal alignment payload emitted by aligned output nodes."""

    data: Mapping[str, Any]
    status: AlignmentStatus
    trigger_ts: int
    partition: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status.ready

    def latest(self) -> "AlignedView":
        return self

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)


AlignedPayload = AlignedView


@dataclass(frozen=True)
class TemporalAlignedOutputSpec:
    """Node output policy that emits aligned payloads from its inputs."""

    trigger: NodeLike
    partition_key: str | None = None
    overrides: Mapping[str, Mapping[str, Any]] | None = None
    watermark_policy: WatermarkPolicy | None = None
    ready_only: bool = True

    def as_config(self) -> dict[str, Any]:
        policy = self.watermark_policy or WatermarkPolicy()
        return {
            "kind": "temporal_aligned",
            "trigger": getattr(self.trigger, "node_id", str(self.trigger)),
            "partition_key": self.partition_key,
            "overrides": _overrides_to_config(self.overrides),
            "watermark_policy": _watermark_policy_to_config(policy),
            "ready_only": self.ready_only,
        }


def duration_to_ms(value: Duration, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(float(value) * 1000)
    match = _DURATION_RE.fullmatch(str(value))
    if not match:
        raise ValueError(f"invalid duration: {value!r}")
    amount, unit = match.groups()
    return int(float(amount) * _DURATION_FACTORS[unit])


def temporal_to_config(value: TemporalSpec | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, TemporalSpec):
        return value.as_config()
    return dict(value)


def alignment_to_config(value: AlignmentInputSpec | Mapping[str, Any]) -> dict[str, Any]:
    spec = _coerce_alignment_spec(value)
    if spec is None:
        raise TypeError("alignment must be an AlignmentInputSpec or mapping")
    return spec.as_config()


def output_to_config(value: TemporalAlignedOutputSpec | Mapping[str, Any]) -> dict[str, Any]:
    spec = _coerce_output_spec(value)
    if spec is None:
        raise TypeError("output must be a TemporalAlignedOutputSpec or mapping")
    return spec.as_config()


def validate_node_output_spec(node: Any) -> None:
    """Validate a node configured with generated temporal output."""

    output = getattr(node, "output", None)
    if output is None:
        return
    if not isinstance(output, TemporalAlignedOutputSpec):
        raise TypeError("unsupported node output spec")
    _require_node_like(output.trigger, role="output trigger")
    if getattr(node, "compute_fn", None) is not None:
        raise TypeError("TemporalAlignedOutputSpec nodes must not define compute_fn")
    inputs = list(getattr(node, "inputs", []) or [])
    if not any(_same_node_interval(candidate, output.trigger) for candidate in inputs):
        raise ValueError("TemporalAlignedOutputSpec trigger must be one of the node inputs")
    inputs_by_alias = _input_mapping_for_output(node, output)
    infer_join_specs(
        inputs_by_alias,
        trigger=output.trigger,
        partition_key=output.partition_key,
        overrides=output.overrides,
    )


def node_has_generated_output(node: Any) -> bool:
    return isinstance(getattr(node, "output", None), TemporalAlignedOutputSpec)


def node_output_should_process(
    node: Any,
    upstream_id: str,
    interval: int,
    *,
    ready: bool,
) -> bool:
    if not ready:
        return False
    output = getattr(node, "output", None)
    if not isinstance(output, TemporalAlignedOutputSpec):
        return ready
    return _is_trigger_event(output.trigger, upstream_id, interval)


def build_node_output(node: Any, view: Any) -> AlignedPayload | None:
    output = getattr(node, "output", None)
    if not isinstance(output, TemporalAlignedOutputSpec):
        raise TypeError("node does not have generated temporal output")
    trigger_entry = _latest_entry(view, output.trigger)
    if trigger_entry is None:
        return None
    trigger_ts, trigger_payload = trigger_entry
    partition = _partition_for_output(output, trigger_payload)
    inputs = _input_mapping_for_output(node, output)
    aligned = align_temporal(
        view,
        inputs,
        trigger=output.trigger,
        trigger_ts=int(trigger_ts),
        partition=partition,
        partition_key=output.partition_key,
        overrides=output.overrides,
        watermark_policy=output.watermark_policy,
    )
    if output.ready_only and not aligned.ready:
        return None
    return aligned


def align_temporal(
    view: Any,
    inputs: Mapping[str, Any],
    *,
    trigger_ts: int,
    trigger: Any | None = None,
    now_ts: int | None = None,
    partition: Mapping[str, Any] | None = None,
    partition_key: str | None = None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
    watermark_policy: WatermarkPolicy | None = None,
) -> AlignedView:
    now = int(trigger_ts if now_ts is None else now_ts)
    specs = infer_join_specs(
        inputs,
        trigger=trigger,
        partition_key=partition_key,
        overrides=overrides,
    )
    values: dict[str, Any] = {}
    statuses: dict[str, AlignmentInputStatus] = {}
    policy = watermark_policy or WatermarkPolicy()
    for name, spec in specs.items():
        value, input_status = _align_one(
            view,
            name=name,
            spec=spec,
            trigger_ts=int(trigger_ts),
            now_ts=now,
            partition=partition or {},
            watermark_policy=policy,
        )
        values[name] = value
        statuses[name] = input_status

    status = _build_status(
        statuses,
        trigger_ts=int(trigger_ts),
        watermark_policy=policy,
    )
    return AlignedView(
        data=values,
        status=status,
        trigger_ts=int(trigger_ts),
        partition=dict(partition or {}),
    )


def infer_join_specs(
    inputs: Mapping[str, Any],
    *,
    trigger: Any | None = None,
    partition_key: str | None = None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, JoinSpec]:
    """Build :class:`JoinSpec` objects from explicit specs or temporal nodes."""

    _validate_override_names(inputs, overrides)
    if any(not isinstance(node, JoinSpec) for node in inputs.values()):
        if trigger is None:
            raise ValueError("trigger is required to infer JoinSpec from nodes")
        trigger = _require_node_like(trigger, role="trigger")
    return {
        name: JoinSpec.infer(
            name,
            node,
            trigger=trigger,
            partition_key=partition_key,
            override=(overrides or {}).get(name),
        )
        for name, node in inputs.items()
    }


def _align_one(
    view: Any,
    *,
    name: str,
    spec: JoinSpec,
    trigger_ts: int,
    now_ts: int,
    partition: Mapping[str, Any],
    watermark_policy: WatermarkPolicy,
) -> tuple[Any, AlignmentInputStatus]:
    entries = _filtered_entries(view, spec, partition)
    selected = _select_entries(entries, spec, trigger_ts)
    if not selected:
        return None, AlignmentInputStatus(
            name=name,
            ready=False,
            reason="missing",
            required=spec.required,
            missing=True,
        )

    selected_ts = selected[-1][0]
    value = selected[-1][1] if spec.mode != "interval" else selected
    age_ms = max(0, now_ts - int(selected_ts)) * 1000
    stale = _is_stale(spec, selected_ts=int(selected_ts), trigger_ts=trigger_ts, age_ms=age_ms)
    late = _is_late(spec, value, trigger_ts=trigger_ts)
    quality = _quality_for(value)
    reason = _input_reason(stale=stale, late=late, quality=quality, policy=watermark_policy)
    return value, AlignmentInputStatus(
        name=name,
        ready=reason is None,
        reason=reason,
        required=spec.required,
        selected_ts=int(selected_ts),
        age_ms=age_ms,
        stale=stale,
        late=late,
        quality=quality,
    )


def _filtered_entries(
    view: Any,
    spec: JoinSpec,
    partition: Mapping[str, Any],
) -> list[tuple[int, Any]]:
    try:
        series_view = view[spec.node][spec.interval_value]
    except KeyError:
        return []
    entries: Sequence[tuple[int, Any]] = _as_sequence(series_view)
    return sorted(
        (
            (int(ts), payload)
            for ts, payload in entries
            if _payload_matches(spec, payload, partition)
        ),
        key=lambda item: item[0],
    )


def _latest_entry(view: Any, node: NodeLike) -> tuple[int, Any] | None:
    try:
        entries: Sequence[tuple[int, Any]] = _as_sequence(
            view[node][parse_interval(node.interval)]
        )
    except KeyError:
        return None
    if not entries:
        return None
    ts, payload = entries[-1]
    return int(ts), payload


def _require_node_like(node: Any, *, role: str) -> Any:
    if not (hasattr(node, "node_id") and hasattr(node, "interval")):
        raise TypeError(f"temporal alignment {role} must be a node, not {type(node).__name__}")
    return node


def _coerce_alignment_spec(
    value: AlignmentInputSpec | Mapping[str, Any] | None,
) -> AlignmentInputSpec | None:
    if value is None or isinstance(value, AlignmentInputSpec):
        return value
    if isinstance(value, Mapping):
        return AlignmentInputSpec(**dict(value))
    raise TypeError("alignment must be an AlignmentInputSpec, mapping, or None")


def _coerce_output_spec(
    value: TemporalAlignedOutputSpec | Mapping[str, Any] | None,
) -> TemporalAlignedOutputSpec | None:
    if value is None or isinstance(value, TemporalAlignedOutputSpec):
        return value
    if isinstance(value, Mapping):
        data = dict(value)
        kind = data.pop("kind", "temporal_aligned")
        if kind != "temporal_aligned":
            raise ValueError(f"unsupported output kind: {kind!r}")
        if "watermark_policy" in data and isinstance(data["watermark_policy"], Mapping):
            data["watermark_policy"] = WatermarkPolicy(**dict(data["watermark_policy"]))
        return TemporalAlignedOutputSpec(**data)
    raise TypeError("output must be a TemporalAlignedOutputSpec, mapping, or None")


def _alignment_for_node(node: Any) -> AlignmentInputSpec | None:
    alignment = getattr(node, "alignment", None)
    if alignment is None:
        config = getattr(node, "config", None)
        if isinstance(config, Mapping):
            alignment = config.get("alignment")
    return _coerce_alignment_spec(alignment)


def _alignment_join_data(node: Any) -> dict[str, Any]:
    alignment = _alignment_for_node(node)
    if alignment is None:
        return {}
    data = {
        "mode": alignment.mode,
        "tolerance": alignment.tolerance,
        "max_age": alignment.max_age,
        "required": alignment.required,
        "closed_only": alignment.closed_only,
        "partition_key": alignment.partition_key,
        "partition_value": alignment.partition_value,
        "calendar": alignment.calendar,
    }
    return {key: value for key, value in data.items() if value is not None}


def _input_mapping_for_output(
    node: Any,
    output: TemporalAlignedOutputSpec,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for input_node in getattr(node, "inputs", []) or []:
        alignment = _alignment_for_node(input_node)
        if alignment is None or alignment.alias is None:
            label = getattr(input_node, "name", None) or getattr(input_node, "node_id", "<unknown>")
            raise ValueError(
                f"TemporalAlignedOutputSpec input {label!r} requires alignment alias"
            )
        alias = str(alignment.alias)
        if alias in result:
            raise ValueError(f"duplicate alignment alias: {alias!r}")
        result[alias] = input_node
    if not result:
        raise ValueError("TemporalAlignedOutputSpec requires at least one input")
    return result


def _partition_for_output(
    output: TemporalAlignedOutputSpec,
    trigger_payload: Any,
) -> dict[str, Any]:
    if output.partition_key is None:
        return {}
    if not isinstance(trigger_payload, Mapping):
        raise ValueError("trigger payload must be a mapping for partitioned temporal output")
    if output.partition_key not in trigger_payload:
        raise ValueError(
            f"trigger payload is missing partition key {output.partition_key!r}"
        )
    return {output.partition_key: trigger_payload[output.partition_key]}


def _is_trigger_event(trigger: Any, upstream_id: str, interval: int) -> bool:
    return (
        hasattr(trigger, "node_id")
        and hasattr(trigger, "interval")
        and upstream_id == trigger.node_id
        and int(interval) == parse_interval(trigger.interval)
    )


def _watermark_policy_to_config(policy: WatermarkPolicy) -> dict[str, Any]:
    return {
        "mode": policy.mode,
        "max_drift": policy.max_drift,
        "late": policy.late,
    }


def _overrides_to_config(
    overrides: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if not overrides:
        return {}
    return {
        name: _join_override_config(override)
        for name, override in overrides.items()
    }


def _join_override_config(override: Mapping[str, Any]) -> dict[str, Any]:
    data = _join_override_data(override)
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, TemporalSpec):
            result[key] = value.as_config()
        elif isinstance(value, CalendarSpec):
            result[key] = value.name
        else:
            result[key] = value
    return result


def _validate_override_names(
    inputs: Mapping[str, Any],
    overrides: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    if not overrides:
        return
    unknown = sorted(set(overrides) - set(inputs))
    if unknown:
        joined = ", ".join(repr(name) for name in unknown)
        raise ValueError(f"JoinSpec overrides reference unknown inputs: {joined}")


def _apply_join_overrides(
    spec: JoinSpec,
    override: Mapping[str, Any] | None,
) -> JoinSpec:
    data = _join_override_data(override)
    return spec if not data else replace(spec, **data)


def _join_override_data(override: Mapping[str, Any] | None) -> dict[str, Any]:
    if override is None:
        return {}
    if not isinstance(override, Mapping):
        raise TypeError("JoinSpec override must be a mapping")
    allowed = set(JoinSpec.__dataclass_fields__) - {"node"}
    unknown = sorted(set(override) - allowed)
    if unknown:
        joined = ", ".join(repr(name) for name in unknown)
        raise ValueError(f"unsupported JoinSpec override field(s): {joined}")
    data = dict(override)
    if "temporal" in data:
        data["temporal"] = _coerce_temporal_spec(data["temporal"])
    if "interval" in data and data["interval"] is not None:
        data["interval"] = parse_interval(data["interval"])
    return data


def _temporal_for_inference(
    name: str,
    node: Any,
    override_data: Mapping[str, Any],
) -> TemporalSpec:
    if "temporal" in override_data:
        temporal = override_data["temporal"]
    else:
        temporal = getattr(node, "temporal", None)
        if temporal is None:
            config = getattr(node, "config", None)
            if isinstance(config, Mapping):
                temporal = config.get("temporal")
    if temporal is None:
        raise ValueError(
            f"cannot infer JoinSpec for input {name!r}: node has no temporal metadata"
        )
    spec = _coerce_temporal_spec(temporal)
    if spec is None:
        raise ValueError(
            f"cannot infer JoinSpec for input {name!r}: node has no temporal metadata"
        )
    return spec


def _coerce_temporal_spec(value: TemporalSpec | Mapping[str, Any] | None) -> TemporalSpec | None:
    if value is None or isinstance(value, TemporalSpec):
        return value
    if isinstance(value, Mapping):
        return TemporalSpec(**dict(value))
    raise TypeError("temporal must be a TemporalSpec, mapping, or None")


def _interval_for_inference(
    name: str,
    node: Any,
    override_data: Mapping[str, Any],
) -> int:
    interval = override_data.get("interval", getattr(node, "interval", None))
    if interval is None:
        raise ValueError(f"cannot infer JoinSpec for input {name!r}: interval is missing")
    return parse_interval(interval)


def _same_node_interval(node: Any, trigger: Any) -> bool:
    if not (hasattr(trigger, "node_id") and hasattr(trigger, "interval")):
        return False
    return (
        node.node_id == trigger.node_id
        and parse_interval(node.interval) == parse_interval(trigger.interval)
    )


def _inferred_join_data(
    *,
    node: Any,
    interval: int,
    temporal: TemporalSpec,
    trigger_input: bool,
    partition_key: str | None,
) -> dict[str, Any]:
    if trigger_input:
        mode: JoinMode = "exact"
        closed_only = temporal.kind == "bar"
    elif temporal.kind == "bar":
        mode = "asof"
        closed_only = True
    elif temporal.kind == "event":
        mode = "asof"
        closed_only = False
    else:
        mode = "temporal"
        closed_only = False
    data = {
        "node": node,
        "interval": interval,
        "mode": mode,
        "closed_only": closed_only,
        "partition_key": partition_key,
        "temporal": temporal,
    }
    if not trigger_input and temporal.kind in {"event", "state"} and temporal.idle_after is not None:
        data["max_age"] = temporal.idle_after
    return data


def _validate_inferred_join_spec(
    name: str,
    spec: JoinSpec,
    *,
    trigger_input: bool,
) -> None:
    if spec.temporal is None:
        raise ValueError(f"cannot infer JoinSpec for input {name!r}: temporal metadata is missing")
    if trigger_input or spec.temporal.kind not in {"event", "state"}:
        return
    if spec.mode not in {"asof", "temporal"}:
        return
    if spec.max_age is not None or spec.tolerance is not None:
        return
    raise ValueError(
        f"cannot infer JoinSpec for input {name!r}: "
        "event/state context inputs require max_age, tolerance, or TemporalSpec.idle_after"
    )


def _unique_nodes(nodes: Sequence[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for node in nodes:
        if not hasattr(node, "node_id"):
            continue
        if node.node_id in seen:
            continue
        seen.add(node.node_id)
        result.append(node)
    return result


def _payload_matches(
    spec: JoinSpec,
    payload: Any,
    partition: Mapping[str, Any],
) -> bool:
    if spec.closed_only and isinstance(payload, Mapping) and payload.get("is_final") is False:
        return False
    if spec.partition_key is None:
        return True
    expected = spec.partition_value
    if expected is None:
        expected = partition.get(spec.partition_key)
    if expected is None:
        return True
    return isinstance(payload, Mapping) and payload.get(spec.partition_key) == expected


def _select_entries(
    entries: Sequence[tuple[int, Any]],
    spec: JoinSpec,
    trigger_ts: int,
) -> list[tuple[int, Any]]:
    if spec.mode == "exact":
        return [item for item in entries if item[0] == trigger_ts]
    if spec.mode in {"asof", "temporal"}:
        before = [item for item in entries if item[0] <= trigger_ts]
        return before[-1:] if before else []
    return _select_interval_entries(entries, spec, trigger_ts)


def _select_interval_entries(
    entries: Sequence[tuple[int, Any]],
    spec: JoinSpec,
    trigger_ts: int,
) -> list[tuple[int, Any]]:
    lookback_ms = spec.tolerance_ms
    if lookback_ms is None:
        lookback_ms = spec.max_age_ms
    if lookback_ms is None:
        return [item for item in entries if item[0] == trigger_ts]
    lower = trigger_ts - int(lookback_ms / 1000)
    return [item for item in entries if lower <= item[0] <= trigger_ts]


def _is_stale(
    spec: JoinSpec,
    *,
    selected_ts: int,
    trigger_ts: int,
    age_ms: int,
) -> bool:
    bounds = [value for value in (spec.max_age_ms, spec.tolerance_ms) if value is not None]
    if not bounds:
        return False
    event_age_ms = max(0, trigger_ts - selected_ts) * 1000
    return any(value < event_age_ms or value < age_ms for value in bounds)


def _is_late(spec: JoinSpec, value: Any, *, trigger_ts: int) -> bool:
    received_ts = _received_ts(spec, value)
    if received_ts is None:
        return False
    allowance_s = int((spec.temporal.max_out_of_order_ms if spec.temporal else 0) / 1000)
    return int(received_ts) > int(trigger_ts) + allowance_s


def _received_ts(spec: JoinSpec, value: Any) -> int | None:
    field = spec.temporal.received_ts if spec.temporal else "received_ts"
    if not field:
        return None
    payload = _latest_payload_for_status(value)
    if not isinstance(payload, Mapping) or field not in payload:
        return None
    return int(payload[field])


def _latest_payload_for_status(value: Any) -> Any:
    if _looks_like_cache_entries(value):
        return value[-1][1] if value else None
    return value


def _quality_for(value: Any) -> str | None:
    if _looks_like_cache_entries(value):
        for _, payload in value:
            quality = _quality_for_payload(payload)
            if quality:
                return quality
        return None
    return _quality_for_payload(value)


def _looks_like_cache_entries(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, Mapping)):
        return False
    return all(
        isinstance(item, Sequence)
        and not isinstance(item, (str, bytes, bytearray))
        and len(item) == 2
        for item in value
    )


def _quality_for_payload(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    if payload.get("sequence_gap") is True:
        return "sequence_gap"
    quality = payload.get("quality")
    if quality is None:
        return None
    quality_text = str(quality)
    return quality_text if quality_text.lower() in _BAD_QUALITY_VALUES else None


def _input_reason(
    *,
    stale: bool,
    late: bool,
    quality: str | None,
    policy: WatermarkPolicy,
) -> str | None:
    if quality is not None:
        return "quality"
    if stale:
        return "stale"
    if late and policy.late != "recompute":
        return "late"
    return None


def _build_status(
    statuses: Mapping[str, AlignmentInputStatus],
    *,
    trigger_ts: int,
    watermark_policy: WatermarkPolicy,
) -> AlignmentStatus:
    blocking = tuple(name for name, status in statuses.items() if not status.ready)
    drift_blocking = _drift_blocking(statuses, watermark_policy)
    reason = _overall_reason(
        blocking=blocking,
        drift_blocking=drift_blocking,
        statuses=statuses,
    )
    return AlignmentStatus(
        ready=reason is None,
        reason=reason,
        trigger_ts=trigger_ts,
        missing_inputs=_missing_inputs(statuses),
        stale_inputs=_stale_inputs(statuses),
        late_inputs=_late_inputs(statuses),
        quality_inputs=_quality_inputs(statuses),
        selected_ts=_selected_ts(statuses),
        age_ms=_age_ms(statuses),
        inputs=dict(statuses),
    )


def _missing_inputs(statuses: Mapping[str, AlignmentInputStatus]) -> tuple[str, ...]:
    return tuple(name for name, status in statuses.items() if status.missing)


def _stale_inputs(statuses: Mapping[str, AlignmentInputStatus]) -> tuple[str, ...]:
    return tuple(name for name, status in statuses.items() if status.stale)


def _late_inputs(statuses: Mapping[str, AlignmentInputStatus]) -> tuple[str, ...]:
    return tuple(name for name, status in statuses.items() if status.late)


def _quality_inputs(statuses: Mapping[str, AlignmentInputStatus]) -> dict[str, str]:
    return {
        name: status.quality
        for name, status in statuses.items()
        if status.quality is not None
    }


def _selected_ts(
    statuses: Mapping[str, AlignmentInputStatus],
) -> dict[str, int | None]:
    return {name: status.selected_ts for name, status in statuses.items()}


def _age_ms(statuses: Mapping[str, AlignmentInputStatus]) -> dict[str, int | None]:
    return {name: status.age_ms for name, status in statuses.items()}


def _drift_blocking(
    statuses: Mapping[str, AlignmentInputStatus],
    watermark_policy: WatermarkPolicy,
) -> tuple[str, ...]:
    max_drift_ms = watermark_policy.max_drift_ms
    if max_drift_ms is None:
        return ()
    ready_ages = {
        name: status.age_ms
        for name, status in statuses.items()
        if status.ready and status.age_ms is not None
    }
    if len(ready_ages) < 2:
        return ()
    fastest = min(ready_ages.values())
    return tuple(
        name
        for name, age in ready_ages.items()
        if age is not None and age - fastest > max_drift_ms
    )


def _overall_reason(
    *,
    blocking: tuple[str, ...],
    drift_blocking: tuple[str, ...],
    statuses: Mapping[str, AlignmentInputStatus],
) -> str | None:
    if drift_blocking:
        return "drift"
    required_blocking = [
        name for name in blocking if _is_required_status(name, statuses)
    ]
    if not required_blocking:
        return None
    return _blocking_reason(required_blocking, statuses)


def _blocking_reason(
    blocking: Sequence[str],
    statuses: Mapping[str, AlignmentInputStatus],
) -> str:
    checks = (
        ("missing_inputs", "missing"),
        ("stale_inputs", "stale"),
        ("late_inputs", "late"),
    )
    for reason, attr in checks:
        if any(getattr(statuses[name], attr) for name in blocking):
            return reason
    return "quality"


def _is_required_status(name: str, statuses: Mapping[str, AlignmentInputStatus]) -> bool:
    return statuses[name].required
