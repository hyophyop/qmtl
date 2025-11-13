from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class WorldMetadataRequest:
    """Instruction for forwarding metadata to WorldService."""

    world_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class HistoryMetadataEnvelope:
    """Normalized metadata required for history updates."""

    node_id: str
    redis_key: str
    redis_payload: dict[str, Any]
    redis_mapping: dict[str, str]
    world_request: WorldMetadataRequest | None


def build_history_metadata_envelope(
    strategy_id: str, report: Any
) -> HistoryMetadataEnvelope:
    """Prepare metadata artifacts for persistence and fan-out.

    The input report originates from compute nodes and can expose attributes
    either directly or nested under ``report.artifact``. This helper extracts
    those values, normalises them into Redis-friendly payloads, and optionally
    prepares a control-plane request for WorldService.
    """

    artifact = getattr(report, "artifact", None)
    dataset_fp = _first_not_none(
        getattr(report, "dataset_fingerprint", None),
        getattr(artifact, "dataset_fingerprint", None) if artifact is not None else None,
    )
    as_of_value = _first_not_none(
        getattr(report, "as_of", None),
        getattr(artifact, "as_of", None) if artifact is not None else None,
    )

    redis_mapping = _build_history_mapping(report, dataset_fp, as_of_value)
    meta_payload = _build_meta_payload(report, artifact, dataset_fp, as_of_value)
    world_request = _build_world_request(strategy_id, report, meta_payload)

    node_id = getattr(report, "node_id")
    return HistoryMetadataEnvelope(
        node_id=node_id,
        redis_key=f"seamless:{node_id}",
        redis_payload=meta_payload,
        redis_mapping=redis_mapping,
        world_request=world_request,
    )


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _build_history_mapping(
    report: Any, dataset_fp: Any, as_of_value: Any
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    world_id = getattr(report, "world_id", None)
    if world_id:
        mapping["compute_world_id"] = str(world_id)
    execution_domain = getattr(report, "execution_domain", None)
    if execution_domain:
        mapping["compute_execution_domain"] = str(execution_domain)
    if as_of_value:
        mapping["compute_as_of"] = str(as_of_value)
    if dataset_fp:
        mapping["compute_dataset_fingerprint"] = str(dataset_fp)
    return mapping


def _build_meta_payload(
    report: Any,
    artifact: Any,
    dataset_fp: Any,
    as_of_value: Any,
) -> dict[str, Any]:
    world_id = getattr(report, "world_id", None)
    execution_domain = getattr(report, "execution_domain", None)
    coverage_bounds = getattr(report, "coverage_bounds", None)
    artifact_payload: Any | None = None
    if artifact is not None:
        model_dump = getattr(artifact, "model_dump", None)
        if callable(model_dump):
            artifact_payload = model_dump()
        else:
            artifact_payload = artifact.__dict__

    payload: dict[str, Any] = {
        "node_id": getattr(report, "node_id"),
        "interval": int(getattr(report, "interval")),
        "rows": getattr(report, "rows", None),
        "coverage_bounds": list(coverage_bounds) if coverage_bounds else None,
        "conformance_flags": getattr(report, "conformance_flags", None) or {},
        "conformance_warnings": getattr(report, "conformance_warnings", None)
        or [],
        "artifact": artifact_payload,
        "dataset_fingerprint": dataset_fp,
        "as_of": as_of_value,
        "updated_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if world_id:
        payload["world_id"] = str(world_id)
    if execution_domain:
        payload["execution_domain"] = str(execution_domain)
    return payload


def _build_world_request(
    strategy_id: str, report: Any, meta_payload: dict[str, Any]
) -> WorldMetadataRequest | None:
    world_id = getattr(report, "world_id", None)
    if not world_id:
        return None
    payload = dict(meta_payload)
    payload["strategy_id"] = strategy_id
    payload["world_id"] = str(world_id)
    return WorldMetadataRequest(world_id=str(world_id), payload=payload)
