from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel


class SeamlessArtifactPayload(BaseModel):
    dataset_fingerprint: str | None = None
    as_of: str | None = None
    rows: int | None = None
    uri: str | None = None


class DecisionEnvelope(BaseModel):
    world_id: str
    policy_version: int
    effective_mode: str
    reason: str | None = None
    as_of: str
    ttl: str
    etag: str
    dataset_fingerprint: str | None = None
    coverage_bounds: List[int] | None = None
    conformance_flags: Dict[str, int] | None = None
    conformance_warnings: List[str] | None = None
    history_updated_at: str | None = None
    rows: int | None = None
    artifact: SeamlessArtifactPayload | None = None


class ActivationEnvelope(BaseModel):
    world_id: str
    strategy_id: str
    side: str
    active: bool
    weight: float
    freeze: bool | None = None
    drain: bool | None = None
    effective_mode: str | None = None
    etag: str
    run_id: str | None = None
    ts: str
    state_hash: str | None = None


__all__ = [
    "ActivationEnvelope",
    "DecisionEnvelope",
    "SeamlessArtifactPayload",
]
