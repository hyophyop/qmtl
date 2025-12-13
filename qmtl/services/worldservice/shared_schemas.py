from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, model_validator

from .policy_engine import Policy


class StrategySeries(BaseModel):
    equity: List[float] | None = None
    pnl: List[float] | None = None
    returns: List[float] | None = None


class SeamlessArtifactPayload(BaseModel):
    dataset_fingerprint: str | None = None
    as_of: str | None = None
    rows: int | None = None
    uri: str | None = None


class EvaluationOverride(BaseModel):
    status: Literal["approved", "rejected", "none"]
    reason: str | None = None
    actor: str | None = None
    timestamp: str | None = None

    @model_validator(mode="after")
    def _require_metadata_for_approved(self) -> "EvaluationOverride":
        if self.status != "approved":
            return self

        missing: list[str] = []
        if not (self.reason and self.reason.strip()):
            missing.append("reason")
        if not (self.actor and self.actor.strip()):
            missing.append("actor")
        if not (self.timestamp and self.timestamp.strip()):
            missing.append("timestamp")

        if missing:
            raise ValueError(
                "approved override requires reason, actor, and timestamp "
                f"(missing: {', '.join(missing)})"
            )
        return self


class ExPostFailureRecord(BaseModel):
    case_id: str | None = None
    status: Literal["candidate", "confirmed"] = "confirmed"
    category: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    severity: Literal["critical", "high", "medium", "low"] | None = None
    evidence_url: str | None = None
    actor: str = Field(min_length=1)
    recorded_at: str | None = None
    source: Literal["manual", "auto"] = "manual"
    notes: str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "ExPostFailureRecord":
        if self.case_id is not None and not str(self.case_id).strip():
            self.case_id = None
        return self


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


class EvaluateRequest(BaseModel):
    metrics: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    previous: List[str] | None = None
    correlations: Dict[tuple[str, str], float] | None = None
    policy: Policy | Dict[str, Any] | None = None
    series: Dict[str, StrategySeries] | None = None
    run_id: str | None = None
    stage: str | None = None
    risk_tier: str | None = None
    strategy_id: str | None = None
    model_card_version: str | None = None
    override: EvaluationOverride | None = None


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
    phase: str | None = None
    requires_ack: bool | None = None
    sequence: int | None = None


__all__ = [
    "ActivationEnvelope",
    "DecisionEnvelope",
    "ExPostFailureRecord",
    "EvaluationOverride",
    "EvaluateRequest",
    "SeamlessArtifactPayload",
    "StrategySeries",
]
