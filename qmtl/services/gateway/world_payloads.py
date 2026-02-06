"""Helpers for shaping WorldService request and response payloads."""
from __future__ import annotations

from typing import Any, Mapping

from qmtl.foundation.common.compute_context import (
    ComputeContext,
    DowngradeReason,
    build_worldservice_compute_context,
    canonicalize_world_mode_alias,
)

from .compute_context import resolve_execution_domain

from . import metrics as gw_metrics


def _record_compute_context_downgrade_metric(context: ComputeContext) -> None:
    if context.downgraded and context.downgrade_reason:
        reason = getattr(context.downgrade_reason, "value", context.downgrade_reason)
        gw_metrics.worlds_compute_context_downgrade_total.labels(reason=reason).inc()


def assemble_compute_context(world_id: str, payload: Mapping[str, Any]) -> ComputeContext:
    """Build and record compute-context metadata for a decision payload."""

    context = build_worldservice_compute_context(world_id, payload)
    _record_compute_context_downgrade_metric(context)
    return context


def _assemble_missing_mode_fallback_context(
    world_id: str, payload: Mapping[str, Any]
) -> ComputeContext:
    context = ComputeContext(
        world_id=world_id,
        execution_domain="backtest",
        as_of=payload.get("as_of"),
        partition=payload.get("partition"),
        dataset_fingerprint=payload.get("dataset_fingerprint")
        or payload.get("datasetFingerprint"),
        downgraded=True,
        downgrade_reason=DowngradeReason.DECISION_UNAVAILABLE,
        safe_mode=True,
    )
    _record_compute_context_downgrade_metric(context)
    return context


def _normalize_effective_mode(payload: dict[str, Any]) -> str | None:
    mode = payload.get("effective_mode")
    if not isinstance(mode, str):
        return None
    canonical = canonicalize_world_mode_alias(mode)
    if canonical is None:
        return mode
    payload["effective_mode"] = canonical
    return canonical


def augment_decision_payload(world_id: str, payload: Any) -> Any:
    """Attach compute-context metadata to decision envelopes when available."""

    if not isinstance(payload, dict):
        return payload
    if "effective_mode" not in payload:
        return payload
    _normalize_effective_mode(payload)

    context = assemble_compute_context(world_id, payload)
    payload["execution_domain"] = context.execution_domain or None
    payload["compute_context"] = context.to_dict(include_flags=True)
    return payload


def augment_activation_payload(payload: Any) -> Any:
    """Attach derived compute-context metadata to activation envelopes."""

    if not isinstance(payload, dict):
        return payload
    world_id = payload.get("world_id")
    effective_mode = _normalize_effective_mode(payload)
    derived_domain = resolve_execution_domain(effective_mode)
    if derived_domain is not None:
        payload["execution_domain"] = derived_domain

    if world_id:
        if effective_mode is None:
            context = _assemble_missing_mode_fallback_context(str(world_id), payload)
        else:
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
