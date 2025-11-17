from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator

from .policy_engine import Policy
from .storage import EXECUTION_DOMAINS, WORLD_NODE_STATUSES


class ExecutionDomainEnum(StrEnum):
    BACKTEST = "backtest"
    DRYRUN = "dryrun"
    LIVE = "live"
    SHADOW = "shadow"


class WorldNodeStatusEnum(StrEnum):
    UNKNOWN = "unknown"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ARCHIVED = "archived"


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
    artifact: SeamlessArtifactPayload | None = None


# --- Rebalancing (multi-world) payloads ---

class PositionSliceModel(BaseModel):
    world_id: str
    strategy_id: str
    symbol: str
    qty: float
    mark: float
    venue: str | None = None


class SymbolDeltaModel(BaseModel):
    symbol: str
    delta_qty: float
    venue: str | None = None


class RebalancePlanModel(BaseModel):
    world_id: str
    scale_world: float
    scale_by_strategy: Dict[str, float]
    deltas: List[SymbolDeltaModel]


class AlphaMetricsEnvelope(BaseModel):
    per_world: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    per_strategy: Dict[str, Dict[str, Dict[str, float]]] = Field(default_factory=dict)


class RebalanceIntentModel(BaseModel):
    """Metadata describing how and why a rebalance was triggered."""

    meta: Dict[str, Any] = Field(default_factory=dict)


class MultiWorldRebalanceRequest(BaseModel):
    total_equity: float
    world_alloc_before: Dict[str, float]
    world_alloc_after: Dict[str, float]
    positions: List[PositionSliceModel]
    # Optional strategy allocations (total-equity basis). If omitted, cascade world scale only.
    strategy_alloc_before_total: Dict[str, Dict[str, float]] | None = None
    strategy_alloc_after_total: Dict[str, Dict[str, float]] | None = None
    min_trade_notional: float | None = None
    lot_size_by_symbol: Dict[str, float] | None = None
    mode: str | None = None  # 'scaling' (default), 'overlay', or 'hybrid'
    overlay: OverlayConfigModel | None = None
    schema_version: int | None = Field(default=None, ge=1)
    rebalance_intent: RebalanceIntentModel | None = None


class MultiWorldRebalanceResponse(BaseModel):
    schema_version: int = 1
    per_world: Dict[str, RebalancePlanModel]
    global_deltas: List[SymbolDeltaModel]
    overlay_deltas: List[SymbolDeltaModel] | None = None
    alpha_metrics: AlphaMetricsEnvelope | None = None
    rebalance_intent: RebalanceIntentModel | None = None
    model_config = ConfigDict()

    def model_dump(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(*args, **kwargs)


class OverlayConfigModel(BaseModel):
    instrument_by_world: Dict[str, str] | None = None
    price_by_symbol: Dict[str, float] | None = None
    min_order_notional: float | None = None

    execution_domain: str | None = None
    updated_at: str | None = None
    artifact: SeamlessArtifactPayload | None = None


class AllocationUpsertRequest(BaseModel):
    """Payload for coordinated world allocation updates."""

    run_id: str
    total_equity: float
    world_allocations: Dict[str, float]
    positions: List[PositionSliceModel]
    strategy_alloc_after_total: Dict[str, Dict[str, float]] | None = None
    strategy_alloc_before_total: Dict[str, Dict[str, float]] | None = None
    min_trade_notional: float | None = None
    lot_size_by_symbol: Dict[str, float] | None = None
    execute: bool = False
    etag: str | None = None
    mode: str | None = None
    overlay: OverlayConfigModel | None = None


class AllocationUpsertResponse(MultiWorldRebalanceResponse):
    """Response emitted after applying world allocation updates."""

    run_id: str
    etag: str
    executed: bool = False
    execution_response: Dict[str, Any] | None = None


__all__ = [
    'AlphaMetricsEnvelope',
    'ActivationEnvelope',
    'ActivationRequest',
    'AllocationUpsertRequest',
    'AllocationUpsertResponse',
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
    'MultiWorldRebalanceRequest',
    'MultiWorldRebalanceResponse',
    'RebalanceIntentModel',
]
