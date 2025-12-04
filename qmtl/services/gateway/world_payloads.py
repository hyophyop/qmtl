"""Helpers for shaping WorldService request and response payloads."""
from __future__ import annotations

from typing import Any, Mapping

from qmtl.foundation.common.compute_context import ComputeContext, build_worldservice_compute_context

from .compute_context import resolve_execution_domain

from . import metrics as gw_metrics


def assemble_compute_context(world_id: str, payload: Mapping[str, Any]) -> ComputeContext:
    """Build and record compute-context metadata for a decision payload."""

    context = build_worldservice_compute_context(world_id, payload)
    if context.downgraded and context.downgrade_reason:
        reason = getattr(context.downgrade_reason, "value", context.downgrade_reason)
        gw_metrics.worlds_compute_context_downgrade_total.labels(reason=reason).inc()
    return context


def augment_decision_payload(world_id: str, payload: Any) -> Any:
    """Attach compute-context metadata to decision envelopes when available."""

    if not isinstance(payload, dict):
        return payload
    if "effective_mode" not in payload:
        return payload

    context = assemble_compute_context(world_id, payload)
    payload["execution_domain"] = context.execution_domain or None
    payload["compute_context"] = context.to_dict(include_flags=True)
    return payload


def augment_activation_payload(payload: Any) -> Any:
    """Attach derived compute-context metadata to activation envelopes."""

    if not isinstance(payload, dict):
        return payload
    world_id = payload.get("world_id")
    effective_mode = payload.get("effective_mode")
    derived_domain = resolve_execution_domain(effective_mode)
    if derived_domain is not None:
        payload["execution_domain"] = derived_domain

    if world_id and effective_mode is not None:
        context = assemble_compute_context(str(world_id), payload)
        payload["compute_context"] = context.to_dict(include_flags=True)
        if context.execution_domain:
            payload["execution_domain"] = context.execution_domain
    return payload


__all__ = [
    "assemble_compute_context",
    "augment_decision_payload",
    "augment_activation_payload",
]
