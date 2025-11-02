from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator

from .policy_engine import Policy
from .storage import EXECUTION_DOMAINS, WORLD_NODE_STATUSES


ExecutionDomainEnum = Enum(
    "ExecutionDomainEnum",
    {value.upper(): value for value in sorted(EXECUTION_DOMAINS)},
    type=str,
)
WorldNodeStatusEnum = Enum(
    "WorldNodeStatusEnum",
    {value.upper(): value for value in sorted(WORLD_NODE_STATUSES)},
    type=str,
)


class StrategySeries(BaseModel):
    equity: List[float] | None = None
    pnl: List[float] | None = None
    returns: List[float] | None = None


class World(BaseModel):
    id: str
    name: str | None = None


class PolicyRequest(BaseModel):
    policy: Policy


class PolicyVersionResponse(BaseModel):
    version: int


class BindingRequest(BaseModel):
    strategies: List[str]


class ActivationRequest(BaseModel):
    strategy_id: str
    side: str
    active: bool
    weight: float | None = None
    freeze: bool | None = None
    drain: bool | None = None
    effective_mode: str | None = None
    run_id: str | None = None
    ts: str | None = None


class ApplyPlan(BaseModel):
    activate: List[str] = Field(default_factory=list)
    deactivate: List[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    metrics: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    previous: List[str] | None = None
    correlations: Dict[tuple[str, str], float] | None = None
    policy: Policy | None = None
    series: Dict[str, StrategySeries] | None = None


class ApplyRequest(EvaluateRequest):
    run_id: str
    plan: ApplyPlan | None = None
    gating_policy: Any | None = None


class ApplyResponse(BaseModel):
    active: List[str]


class ApplyAck(BaseModel):
    ok: bool = True
    run_id: str
    active: List[str]
    phase: str | None = None


class DecisionsRequest(BaseModel):
    """Canonical payload for updating the active strategy decisions of a world."""

    strategies: List[str] = Field(..., description="Ordered list of strategy identifiers", min_length=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _normalize(self) -> "DecisionsRequest":
        seen: set[str] = set()
        normalized: list[str] = []
        for raw in self.strategies:
            value = str(raw).strip()
            if not value:
                raise ValueError("strategies entries must be non-empty strings")
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        self.strategies = normalized
        return self


class BindingsResponse(BaseModel):
    strategies: List[str]


class WorldNodeRef(BaseModel):
    world_id: str
    node_id: str
    execution_domain: ExecutionDomainEnum
    status: WorldNodeStatusEnum
    last_eval_key: str | None = None
    annotations: Dict[str, Any] | None = None


class WorldNodeUpsertRequest(BaseModel):
    status: WorldNodeStatusEnum
    execution_domain: ExecutionDomainEnum | None = None
    last_eval_key: str | None = None
    annotations: Dict[str, Any] | None = None


class EdgeOverrideResponse(BaseModel):
    world_id: str
    src_node_id: str
    dst_node_id: str
    active: bool
    reason: str | None = None
    updated_at: str | None = None


class EdgeOverrideUpsertRequest(BaseModel):
    active: bool
    reason: str | None = None


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


class ValidationCacheContext(BaseModel):
    node_id: str
    execution_domain: str
    contract_id: str
    dataset_fingerprint: str
    code_version: str
    resource_policy: str


class ValidationCacheLookupRequest(ValidationCacheContext):
    pass


class ValidationCacheStoreRequest(ValidationCacheContext):
    result: Literal['valid', 'invalid', 'warning']
    metrics: Dict[str, Any]
    timestamp: str | None = None


class ValidationCacheResponse(BaseModel):
    cached: bool
    eval_key: str | None = None
    result: str | None = None
    metrics: Dict[str, Any] | None = None
    timestamp: str | None = None


class SeamlessArtifactPayload(BaseModel):
    dataset_fingerprint: str | None = None
    as_of: str | None = None
    rows: int | None = None
    uri: str | None = None


class SeamlessHistoryRequest(BaseModel):
    strategy_id: str
    node_id: str
    interval: int
    rows: int | None = None
    coverage_bounds: tuple[int, int] | None = None
    conformance_flags: Dict[str, int] | None = None
    conformance_warnings: List[str] | None = None
    dataset_fingerprint: str | None = None
    as_of: str | None = None
    execution_domain: str | None = None
    updated_at: str | None = None
    artifact: SeamlessArtifactPayload | None = None


__all__ = [
    'ActivationEnvelope',
    'ActivationRequest',
    'ApplyAck',
    'ApplyPlan',
    'ApplyRequest',
    'ApplyResponse',
    'BindingRequest',
    'BindingsResponse',
    'DecisionEnvelope',
    'DecisionsRequest',
    'EdgeOverrideResponse',
    'EdgeOverrideUpsertRequest',
    'EvaluateRequest',
    'ExecutionDomainEnum',
    'PolicyRequest',
    'PolicyVersionResponse',
    'StrategySeries',
    'ValidationCacheLookupRequest',
    'ValidationCacheResponse',
    'ValidationCacheStoreRequest',
    'SeamlessArtifactPayload',
    'SeamlessHistoryRequest',
    'World',
    'WorldNodeRef',
    'WorldNodeStatusEnum',
    'WorldNodeUpsertRequest',
]
