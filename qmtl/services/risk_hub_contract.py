"""Shared contract utilities for Risk Signal Hub snapshots.

This module is used by both producers (e.g., gateway/risk engines) and
consumers (WorldService) to enforce consistent snapshot validation and
hashing rules.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from qmtl.foundation.common.hashutils import hash_bytes


DEFAULT_REALIZED_RETURNS_MAX_POINTS_PER_SERIES = 200_000
DEFAULT_REALIZED_RETURNS_MAX_POINTS_TOTAL = 1_000_000


def stable_snapshot_hash(payload: Mapping[str, Any]) -> str:
    """Compute a deterministic hash for a snapshot payload.

    Volatile fields such as ``created_at`` and any existing ``hash`` value are
    excluded so that retries produce the same digest.
    """

    canonical = dict(payload)
    canonical.pop("hash", None)
    canonical.pop("created_at", None)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hash_bytes(encoded)


def risk_snapshot_dedupe_key(payload: Mapping[str, Any]) -> str:
    """Return stable idempotency key for a risk hub snapshot payload.

    The key is built from ``(world_id, version, hash, actor, stage)`` where
    ``hash`` falls back to :func:`stable_snapshot_hash` when missing.
    """

    world_id = str(payload.get("world_id") or "")
    version = str(payload.get("version") or "")
    provenance = payload.get("provenance")
    actor = ""
    stage = ""
    if isinstance(provenance, Mapping):
        actor = str(provenance.get("actor") or "")
        stage = str(provenance.get("stage") or "")
    snap_hash = payload.get("hash")
    if not isinstance(snap_hash, str) or not snap_hash:
        try:
            snap_hash = stable_snapshot_hash(payload)
        except Exception:
            serialized = repr(sorted(payload.items(), key=lambda kv: kv[0])).encode()
            snap_hash = hash_bytes(serialized)
    return "|".join([world_id, version, str(snap_hash), actor, stage])


def normalize_and_validate_snapshot(
    world_id: str,
    payload: Mapping[str, Any],
    *,
    actor: str | None = None,
    stage: str | None = None,
    ttl_sec_default: int = 900,
    ttl_sec_max: int = 86400,
    allowed_actors: Sequence[str] | None = None,
    allowed_stages: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a snapshot payload and fill derived fields.

    - Ensures required fields exist.
    - Enforces weights to be normalized (sum≈1.0).
    - Validates/sets ttl_sec.
    - Injects provenance.actor/stage when provided.
    - Computes stable hash when missing.
    """

    data: dict[str, Any] = dict(payload)

    if world_id:
        data["world_id"] = world_id
    else:
        world_id = str(data.get("world_id") or "")
    if not world_id:
        raise ValueError("world_id is required")

    as_of = data.get("as_of")
    if not isinstance(as_of, str) or not as_of:
        raise ValueError("as_of is required")
    _validate_iso_timestamp(as_of)

    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("version is required")

    weights = data.get("weights")
    if not isinstance(weights, Mapping) or not weights:
        raise ValueError("weights are required")
    try:
        weight_sum = sum(float(v) for v in weights.values())
    except Exception as exc:
        raise ValueError("weights must be numeric") from exc
    if weight_sum <= 0 or abs(weight_sum - 1.0) > 1e-3:
        raise ValueError("weights must sum to ~1.0")

    ttl = data.get("ttl_sec", ttl_sec_default)
    if ttl is not None:
        try:
            ttl_int = int(ttl)
        except Exception as exc:
            raise ValueError("ttl_sec must be an integer") from exc
        if ttl_int <= 0:
            raise ValueError("ttl_sec must be positive")
        if ttl_sec_max is not None and ttl_int > int(ttl_sec_max):
            raise ValueError(f"ttl_sec must be <= {int(ttl_sec_max)}")
        data["ttl_sec"] = ttl_int

    _normalize_and_validate_realized_returns(
        data,
        max_points_per_series=DEFAULT_REALIZED_RETURNS_MAX_POINTS_PER_SERIES,
        max_points_total=DEFAULT_REALIZED_RETURNS_MAX_POINTS_TOTAL,
    )

    provenance = data.get("provenance")
    provenance_map: dict[str, Any] = dict(provenance) if isinstance(provenance, Mapping) else {}

    if actor is not None:
        existing = provenance_map.get("actor")
        if existing is not None and str(existing) != str(actor):
            raise ValueError("actor mismatch between payload and header")
        provenance_map["actor"] = str(actor)

    if stage is not None:
        existing = provenance_map.get("stage")
        if existing is not None and str(existing) != str(stage):
            raise ValueError("stage mismatch between payload and header")
        provenance_map["stage"] = str(stage)

    actor_value = str(provenance_map.get("actor") or "")
    _validate_actor(actor_value, allowed_actors=allowed_actors)

    stage_value = str(provenance_map.get("stage") or "")
    _validate_stage(stage_value, allowed_stages=allowed_stages)

    if provenance_map:
        data["provenance"] = provenance_map

    existing_hash = data.get("hash")
    if existing_hash is not None and not isinstance(existing_hash, str):
        raise ValueError("hash must be a string when provided")
    computed_hash = stable_snapshot_hash(data)
    if isinstance(existing_hash, str) and existing_hash and existing_hash != computed_hash:
        raise ValueError("hash mismatch")
    data["hash"] = existing_hash if isinstance(existing_hash, str) and existing_hash else computed_hash

    return data


def _normalize_and_validate_realized_returns(
    data: dict[str, Any],
    *,
    max_points_per_series: int,
    max_points_total: int,
) -> None:
    realized_ref = data.get("realized_returns_ref")
    if realized_ref is not None and not (isinstance(realized_ref, str) and realized_ref.strip()):
        raise ValueError("realized_returns_ref must be a non-empty string when provided")
    if isinstance(realized_ref, str):
        data["realized_returns_ref"] = realized_ref.strip()

    realized = data.get("realized_returns")
    if realized is None:
        return

    normalized = normalize_realized_returns(
        realized,
        max_points_per_series=max_points_per_series,
        max_points_total=max_points_total,
    )
    data["realized_returns"] = normalized


def normalize_realized_returns(
    realized: Any,
    *,
    max_points_per_series: int = DEFAULT_REALIZED_RETURNS_MAX_POINTS_PER_SERIES,
    max_points_total: int = DEFAULT_REALIZED_RETURNS_MAX_POINTS_TOTAL,
) -> dict[str, list[float]] | list[float]:
    """Validate and normalize realized_returns payload into JSON-stable primitives.

    Accepted shapes:
    - ``{"<strategy_id>": [r1, r2, ...], ...}``
    - ``[r1, r2, ...]`` (single series; discouraged but supported for compatibility)

    Normalization:
    - Values are coerced to finite floats.
    - Non-finite values and booleans are rejected.
    - Hard caps prevent accidental multi-megabyte inline payloads.
    """

    if isinstance(realized, Mapping):
        normalized: dict[str, list[float]] = {}
        total_points = 0
        for raw_key, raw_series in realized.items():
            key = str(raw_key or "").strip()
            if not key:
                raise ValueError("realized_returns keys must be non-empty strings")
            series = _normalize_float_series(raw_series, context=f"realized_returns[{key}]")
            if len(series) > int(max_points_per_series):
                raise ValueError(f"realized_returns series too long for '{key}'")
            total_points += len(series)
            if total_points > int(max_points_total):
                raise ValueError("realized_returns total points exceed limit")
            normalized[key] = series
        if not normalized:
            raise ValueError("realized_returns must be non-empty when provided")
        return normalized

    if isinstance(realized, Sequence) and not isinstance(realized, (str, bytes, bytearray)):
        series = _normalize_float_series(realized, context="realized_returns")
        if len(series) > int(max_points_total):
            raise ValueError("realized_returns series too long")
        return series

    raise ValueError("realized_returns must be a mapping[str, sequence[float]] or a sequence[float]")


def _normalize_float_series(raw: Any, *, context: str) -> list[float]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError(f"{context} must be a sequence of finite floats")
    normalized: list[float] = []
    for value in raw:
        if isinstance(value, bool):
            raise ValueError(f"{context} contains invalid boolean value")
        try:
            candidate = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context} contains non-numeric value") from exc
        if not math.isfinite(candidate):
            raise ValueError(f"{context} contains non-finite value")
        normalized.append(candidate)
    if not normalized:
        raise ValueError(f"{context} must be non-empty")
    return normalized


def _validate_actor(actor: str, *, allowed_actors: Sequence[str] | None) -> None:
    if not actor:
        raise ValueError("actor is required")
    if allowed_actors is not None and actor not in allowed_actors:
        raise ValueError(f"actor '{actor}' not allowed")


def _validate_stage(stage: str, *, allowed_stages: Sequence[str] | None) -> None:
    if not stage:
        raise ValueError("stage is required")
    if allowed_stages is not None and stage not in allowed_stages:
        raise ValueError(f"stage '{stage}' not allowed")


def _validate_iso_timestamp(value: str) -> None:
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(text)
    except Exception as exc:
        raise ValueError(f"invalid as_of timestamp: {value}") from exc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)


__all__ = [
    "DEFAULT_REALIZED_RETURNS_MAX_POINTS_PER_SERIES",
    "DEFAULT_REALIZED_RETURNS_MAX_POINTS_TOTAL",
    "normalize_and_validate_snapshot",
    "normalize_realized_returns",
    "risk_snapshot_dedupe_key",
    "stable_snapshot_hash",
]
