"""Shared contract utilities for Risk Signal Hub snapshots.

This module is used by both producers (e.g., gateway/risk engines) and
consumers (WorldService) to enforce consistent snapshot validation and
hashing rules.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from qmtl.foundation.common.hashutils import hash_bytes


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
    ttl_sec_default: int = 10,
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
        data["ttl_sec"] = ttl_int

    provenance = data.get("provenance")
    provenance_map: dict[str, Any] = dict(provenance) if isinstance(provenance, Mapping) else {}

    actor_value = actor or provenance_map.get("actor")
    stage_value = stage or provenance_map.get("stage")

    if allowed_actors is not None:
        _validate_actor(str(actor_value or ""), allowed_actors=allowed_actors)
    elif actor_value:
        _validate_actor(str(actor_value), allowed_actors=None)

    if allowed_stages is not None:
        _validate_stage(str(stage_value or ""), allowed_stages=allowed_stages)
    elif stage_value:
        _validate_stage(str(stage_value), allowed_stages=None)

    if actor_value:
        provenance_map.setdefault("actor", str(actor_value))
    if stage_value:
        provenance_map.setdefault("stage", str(stage_value))
    if provenance_map:
        data["provenance"] = provenance_map

    if not data.get("hash"):
        data["hash"] = stable_snapshot_hash(data)

    return data


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
    "normalize_and_validate_snapshot",
    "risk_snapshot_dedupe_key",
    "stable_snapshot_hash",
]
