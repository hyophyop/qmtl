from __future__ import annotations

from typing import Any, Mapping

from opentelemetry import trace

_COMMON_KEYS = (
    "world_id",
    "execution_domain",
    "run_id",
    "etag",
    "strategy_id",
    "request_id",
    "decision_id",
)


def build_observability_fields(**values: Any) -> dict[str, Any]:
    """Return a compact dict with non-empty observability fields."""

    fields: dict[str, Any] = {}
    for key in _COMMON_KEYS:
        value = values.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                continue
            fields[key] = cleaned
        else:
            fields[key] = value
    return fields


def add_span_attributes(fields: Mapping[str, Any]) -> None:
    """Attach observability fields to the current span if recording."""

    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return
    for key, value in fields.items():
        span.set_attribute(key, value)

