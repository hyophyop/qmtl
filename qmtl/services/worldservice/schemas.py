from __future__ import annotations

from enum import StrEnum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .policy_engine import Policy
from .shared_schemas import (
    ActivationEnvelope,
    DecisionEnvelope,
    EvaluateRequest,
    EvaluationOverride,
    SeamlessArtifactPayload,
    StrategySeries,
)


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


class World(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    description: str | None = None
    owner: str | None = None
    labels: List[str] = Field(default_factory=list)
    state: Literal["ACTIVE", "SUSPENDED", "DELETED"] = "ACTIVE"
    allow_live: bool = False
    circuit_breaker: bool = False
    default_policy_version: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PolicyRequest(BaseModel):
    preset: str | None = None
    preset_mode: str | None = None
    preset_version: str | None = None
    preset_overrides: Dict[str, float] | None = None
    policy: Policy | dict | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "PolicyRequest":
        if self.policy is not None and not isinstance(self.policy, Policy):
            try:
                self.policy = Policy.model_validate(self.policy)
            except Exception as exc:
                raise ValueError(f"invalid policy payload: {exc}") from exc

        if self.preset:
            try:
                from .presets import get_preset_policy
                preset_policy = get_preset_policy(self.preset, self.preset_overrides)
                self.policy = self.policy or preset_policy
            except Exception as exc:
                raise ValueError(f"invalid preset '{self.preset}': {exc}") from exc

        if self.policy is None:
            raise ValueError("policy is required")
        return self

    def to_payload(self) -> Dict[str, Any]:
        """Serialize to storage-friendly payload with metadata."""
        return {
            "preset": self.preset,
            "preset_mode": self.preset_mode,
            "preset_version": self.preset_version,
            "overrides": self.preset_overrides,
            "policy": self.policy.model_dump() if isinstance(self.policy, Policy) else self.policy,
        }


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


class ApplyRequest(EvaluateRequest):
    run_id: str
    plan: ApplyPlan | None = None
    gating_policy: Any | None = None


class ApplyResponse(BaseModel):
    active: List[str]
    evaluation_run_id: str | None = None
    evaluation_run_url: str | None = None


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


class WorldAllocationSnapshot(BaseModel):
    """Latest allocation ratios for a world."""

    world_id: str
    allocation: float
    run_id: str | None = None
    etag: str | None = None
    strategy_alloc_total: Dict[str, float] | None = None
    updated_at: str | None = None
    ttl: str | None = None
    stale: bool = False


class AllocationSnapshotResponse(BaseModel):
    """Collection of world allocation snapshots keyed by world id."""

    allocations: Dict[str, WorldAllocationSnapshot] = Field(default_factory=dict)


class ReturnsMetrics(BaseModel):
    sharpe: float | None = None
    max_drawdown: float | None = None
    gain_to_pain_ratio: float | None = None
    time_under_water_ratio: float | None = None


class SampleMetrics(BaseModel):
    effective_history_years: float | None = None
    n_trades_total: int | None = None
    n_trades_per_year: float | None = None


class RiskMetrics(BaseModel):
    adv_utilization_p95: float | None = None
    participation_rate_p95: float | None = None


class RobustnessMetrics(BaseModel):
    deflated_sharpe_ratio: float | None = None
    sharpe_first_half: float | None = None
    sharpe_second_half: float | None = None


class ValidationHealth(BaseModel):
    metric_coverage_ratio: float | None = None
    rules_executed_ratio: float | None = None


class DiagnosticsMetrics(BaseModel):
    strategy_complexity: float | None = None
    search_intensity: int | None = None
    returns_source: str | None = None
    validation_health: ValidationHealth | None = None


class EvaluationMetrics(BaseModel):
    returns: ReturnsMetrics | None = None
    sample: SampleMetrics | None = None
    risk: RiskMetrics | None = None
    robustness: RobustnessMetrics | None = None
    diagnostics: DiagnosticsMetrics | None = None


class RuleResultModel(BaseModel):
    status: Literal["pass", "fail", "warn"]
    severity: Literal["blocking", "soft", "info"] | None = None
    owner: Literal["quant", "risk", "ops"] | None = None
    reason_code: str | None = None
    reason: str | None = None
    tags: List[str] | None = None
    details: Dict[str, Any] | None = None


class EvaluationValidation(BaseModel):
    policy_version: str | None = None
    ruleset_hash: str | None = None
    profile: str | None = None
    results: Dict[str, RuleResultModel] | None = None


class EvaluationSummary(BaseModel):
    status: Literal["pass", "warn", "fail"] | None = None
    recommended_stage: Literal[
        "backtest_only", "paper_only", "paper_ok_live_candidate"
    ] | None = None
    override_status: Literal["none", "approved", "rejected"] | None = None
    override_reason: str | None = None
    override_actor: str | None = None
    override_timestamp: str | None = None


class EvaluationRunModel(BaseModel):
    world_id: str
    strategy_id: str
    run_id: str
    stage: Literal["backtest", "paper", "live"] | str
    risk_tier: Literal["high", "medium", "low"] | str
    model_card_version: str | None = None
    metrics: EvaluationMetrics | None = None
    validation: EvaluationValidation | None = None
    summary: EvaluationSummary | None = None
    created_at: str | None = None
    updated_at: str | None = None


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
    'EvaluationOverride',
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
    'RebalancePlanModel',
    'SymbolDeltaModel',
    'WorldAllocationSnapshot',
    'AllocationSnapshotResponse',
    'ReturnsMetrics',
    'SampleMetrics',
    'RiskMetrics',
    'RobustnessMetrics',
    'DiagnosticsMetrics',
    'ValidationHealth',
    'EvaluationMetrics',
    'RuleResultModel',
    'EvaluationValidation',
    'EvaluationSummary',
    'EvaluationRunModel',
]
