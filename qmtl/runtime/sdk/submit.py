"""Simplified strategy submission API.

This module provides the new unified submission interface for QMTL v2.0.
All legacy APIs (Runner.run, Runner.offline) are replaced by Runner.submit().

Phase 2 Enhancements:
- Automatic validation pipeline integration
- Performance metrics calculation from backtest
- Threshold-based auto-activation
- Real contribution/weight/rank feedback

Phase 3 Enhancements:
- ExecutionDomain unified to single Mode concept
- Uses qmtl.runtime.sdk.mode for mode utilities
"""

from __future__ import annotations

import asyncio
import logging
import numbers
import os
from decimal import Decimal
from threading import Thread
from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING, Any, Coroutine, Sequence, SupportsFloat

import httpx

if TYPE_CHECKING:
    from .strategy import Strategy
    from .gateway_client import GatewayClient
    from .services import RunnerServices

from .mode import Mode, mode_to_execution_domain
from .services import get_global_services
from .world_data import (
    WorldDataSelection,
    apply_data_binding,
    build_provider_binding,
    resolve_world_data_selection,
)
from qmtl.services.worldservice.shared_schemas import ActivationEnvelope, DecisionEnvelope

logger = logging.getLogger(__name__)

# Re-export Mode for backward compatibility
__all__ = [
    "Mode",
    "SubmitResult",
    "AllocationSnapshot",
    "PrecheckResult",
    "StrategyMetrics",
    "AutoReturnsConfig",
    "submit",
    "submit_async",
]


@dataclass
class StrategyMetrics:
    """Performance metrics for a submitted strategy."""
    sharpe: float | None = None
    max_drawdown: float | None = None
    correlation_avg: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    car_mdd: float | None = None
    rar_mdd: float | None = None
    total_return: float | None = None
    num_trades: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "correlation_avg": self.correlation_avg,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "car_mdd": self.car_mdd,
            "rar_mdd": self.rar_mdd,
            "total_return": self.total_return,
            "num_trades": self.num_trades,
        }


@dataclass
class PrecheckResult:
    """Local ValidationPipeline pre-check output (non-SSOT)."""
    status: str
    activated: bool = False
    weight: float | None = None
    rank: int | None = None
    contribution: float | None = None
    metrics: StrategyMetrics = field(default_factory=StrategyMetrics)
    violations: list[dict[str, object]] = field(default_factory=list)
    improvement_hints: list[str] = field(default_factory=list)
    correlation_avg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "activated": self.activated,
            "weight": self.weight,
            "rank": self.rank,
            "contribution": self.contribution,
            "metrics": self.metrics.to_dict(),
            "violations": self.violations,
            "improvement_hints": self.improvement_hints,
            "correlation_avg": self.correlation_avg,
        }


@dataclass
class AllocationSnapshot:
    """Latest world allocation snapshot for a submitted world."""

    world_id: str
    allocation: float | None = None
    run_id: str | None = None
    etag: str | None = None
    strategy_alloc_total: dict[str, float] | None = None
    updated_at: str | None = None
    stale: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "world_id": self.world_id,
            "allocation": self.allocation,
            "run_id": self.run_id,
            "etag": self.etag,
            "updated_at": self.updated_at,
        }
        if self.strategy_alloc_total is not None:
            payload["strategy_alloc_total"] = dict(self.strategy_alloc_total)
        if self.stale is not None:
            payload["stale"] = self.stale
        return payload


@dataclass
class AllocationSnapshotResult:
    """Fetch outcome for an allocation snapshot."""

    snapshot: AllocationSnapshot | None
    notice: str | None = None
    stale: bool = False


@dataclass
class SubmitResult:
    """Result of strategy submission.
    
    This provides immediate feedback on strategy submission including
    activation status and contribution to world returns.
    """
    strategy_id: str
    status: str  # "pending" | "validating" | "active" | "rejected"
    world: str
    mode: Mode
    downgraded: bool = False
    downgrade_reason: str | None = None
    safe_mode: bool = False
    
    # Contribution to world (populated after validation)
    contribution: float | None = None  # Contribution to world returns
    weight: float | None = None  # Portfolio weight
    rank: int | None = None  # Rank within world

    # Performance metrics
    metrics: StrategyMetrics = field(default_factory=StrategyMetrics)

    # WS envelopes (shared schema)
    decision: DecisionEnvelope | None = None
    activation: ActivationEnvelope | None = None
    allocation: "AllocationSnapshot | None" = None
    allocation_notice: str | None = None
    allocation_stale: bool = False
    
    # Rejection info (if status == "rejected")
    rejection_reason: str | None = None
    improvement_hints: list[str] = field(default_factory=list)
    
    # Threshold violations (for rejected strategies)
    threshold_violations: list[dict] = field(default_factory=list)
    
    # Internal reference to the instantiated strategy (for debugging/tests)
    strategy: "Strategy | None" = None
    # Local validation/pre-check outputs (not SSOT; WS is authoritative)
    precheck: PrecheckResult | None = None

    def to_dict(self) -> dict[str, Any]:
        def _dump_model(model: Any) -> Any:
            if model is None:
                return None
            if hasattr(model, "model_dump"):
                return model.model_dump()
            if hasattr(model, "dict"):
                return model.dict()
            return model

        mode_value = self.mode.value if hasattr(self.mode, "value") else str(self.mode)
        metrics_dump = self.metrics.to_dict()
        decision_dump = _dump_model(self.decision)
        activation_dump = _dump_model(self.activation)
        if self.allocation is not None:
            try:
                allocation_dump = self.allocation.to_dict()
            except Exception:
                allocation_dump = None
        else:
            allocation_dump = None
        improvement_hints = list(self.improvement_hints)
        threshold_violations = list(self.threshold_violations)

        payload = {
            "strategy_id": self.strategy_id,
            "status": self.status,
            "world": self.world,
            "mode": mode_value,
            "downgraded": self.downgraded,
            "downgrade_reason": self.downgrade_reason,
            "safe_mode": self.safe_mode,
            "contribution": self.contribution,
            "weight": self.weight,
            "rank": self.rank,
            "metrics": metrics_dump,
            "decision": decision_dump,
            "activation": activation_dump,
            "rejection_reason": self.rejection_reason,
            "improvement_hints": improvement_hints,
            "threshold_violations": threshold_violations,
            "precheck": self.precheck.to_dict() if self.precheck else None,
            "allocation": allocation_dump,
            "allocation_notice": self.allocation_notice,
            "allocation_stale": self.allocation_stale,
        }

        payload["ws"] = {
            "strategy_id": self.strategy_id,
            "world": self.world,
            "status": self.status,
            "mode": mode_value,
            "decision": decision_dump,
            "activation": activation_dump,
            "allocation": allocation_dump,
            "contribution": self.contribution,
            "weight": self.weight,
            "rank": self.rank,
            "metrics": metrics_dump,
            "rejection_reason": self.rejection_reason,
            "improvement_hints": improvement_hints,
            "threshold_violations": threshold_violations,
            "downgraded": self.downgraded,
            "downgrade_reason": self.downgrade_reason,
            "safe_mode": self.safe_mode,
        }
        return payload

    def __post_init__(self) -> None:
        if self.decision:
            self.world = self.decision.world_id

        if self.activation:
            self.world = self.activation.world_id
            self.strategy_id = self.activation.strategy_id
            if self.weight is None:
                self.weight = self.activation.weight


@dataclass(frozen=True)
class AutoReturnsConfig:
    """Configuration for deriving returns automatically.

    Attributes
    ----------
    price_attributes : tuple[str, ...]
        Ordered list of attribute names to inspect on the strategy for price/equity
        series suitable for deriving percentage returns.
    min_length : int
        Minimum series length required to derive returns (at least two points).
    """

    price_attributes: tuple[str, ...] = (
        "prices",
        "price_series",
        "price_history",
        "close_prices",
        "close",
    )
    min_length: int = 2


# Default configuration
DEFAULT_WORLD = "__default__"
DEFAULT_GATEWAY_URL = "http://localhost:8000"
DEFAULT_PRESET = "sandbox"  # Use sandbox preset for zero-config submissions

# Environment variable names
ENV_GATEWAY_URL = "QMTL_GATEWAY_URL"
ENV_DEFAULT_WORLD = "QMTL_DEFAULT_WORLD"
ENV_DEFAULT_PRESET = "QMTL_DEFAULT_PRESET"


def _get_gateway_url(world: str | None = None) -> str:
    """Get gateway URL from environment or use default."""
    explicit = os.environ.get(ENV_GATEWAY_URL)
    if explicit:
        return explicit
    if world and world != DEFAULT_WORLD:
        return os.environ.get("GATEWAY_URL") or DEFAULT_GATEWAY_URL
    return DEFAULT_GATEWAY_URL


def _get_default_world() -> str:
    """Get default world from environment or use default."""
    from qmtl.runtime.sdk.configuration import get_runtime_config

    config = get_runtime_config()
    if config and config.project.default_world:
        return config.project.default_world
    return os.environ.get(ENV_DEFAULT_WORLD, DEFAULT_WORLD)


def _normalize_world_id(world: str | None) -> str:
    """Normalize and validate world identifier."""
    candidate = (world or "").strip()
    if not candidate:
        raise ValueError(
            "world must be provided; set --world or QMTL_DEFAULT_WORLD / project.default_world"
        )
    return candidate


def _world_id_candidates(world_id: str) -> tuple[str, ...]:
    variants = [world_id, world_id.replace("_", "-"), world_id.replace("-", "_")]
    seen: dict[str, str] = {}
    for val in variants:
        if val not in seen:
            seen[val] = val
    return tuple(seen.keys())


def _get_default_preset() -> str:
    """Get default preset from environment or use default."""
    return os.environ.get(ENV_DEFAULT_PRESET, DEFAULT_PRESET)


def _policy_to_human_readable(policy: Any) -> str:
    """Convert a policy-like dict to a concise human readable string."""
    data, preset = _extract_policy_data(policy)
    parts: list[str] = []
    if preset:
        parts.append(f"preset={preset}")
    parts.extend(_render_thresholds(data))
    parts.extend(_render_top_k(data))
    parts.extend(_render_correlation_limit(data))
    parts.extend(_render_hysteresis(data))
    return ", ".join(parts) if parts else "no policy"


def _extract_policy_data(policy: Any) -> tuple[dict[str, Any], str | None]:
    """Return (policy_dict, preset)."""
    if policy is None:
        return {}, None
    if isinstance(policy, dict):
        data = policy.get("policy") if "policy" in policy else policy
        return data if isinstance(data, dict) else {}, policy.get("preset")
    try:
        return policy.model_dump(), None
    except Exception:
        return {}, None


def _render_thresholds(data: dict[str, Any]) -> list[str]:
    thresholds = data.get("thresholds") if isinstance(data, dict) else None
    if not isinstance(thresholds, dict):
        return []
    bits: list[str] = []
    for metric, cfg in thresholds.items():
        if not isinstance(cfg, dict):
            continue
        min_v = cfg.get("min")
        max_v = cfg.get("max")
        if min_v is not None and max_v is not None:
            bits.append(f"{metric} between {min_v} and {max_v}")
        elif min_v is not None:
            bits.append(f"{metric} >= {min_v}")
        elif max_v is not None:
            bits.append(f"{metric} <= {max_v}")
    return ["thresholds: " + "; ".join(bits)] if bits else []


def _render_top_k(data: dict[str, Any]) -> list[str]:
    top_k = data.get("top_k") if isinstance(data, dict) else None
    if not isinstance(top_k, dict):
        return []
    metric = top_k.get("metric")
    k = top_k.get("k")
    if metric and k:
        return [f"top_k: keep top {k} by {metric}"]
    return []


def _render_correlation_limit(data: dict[str, Any]) -> list[str]:
    corr = data.get("correlation") if isinstance(data, dict) else None
    if isinstance(corr, dict) and corr.get("max") is not None:
        return [f"correlation max: {corr.get('max')}"]
    return []


def _render_hysteresis(data: dict[str, Any]) -> list[str]:
    hyst = data.get("hysteresis") if isinstance(data, dict) else None
    metric = hyst.get("metric") if isinstance(hyst, dict) else None
    enter = hyst.get("enter") if isinstance(hyst, dict) else None
    exit_v = hyst.get("exit") if isinstance(hyst, dict) else None
    if metric and enter is not None and exit_v is not None:
        return [f"hysteresis on {metric}: enter {enter}, exit {exit_v}"]
    return []


def _run_coroutine_blocking(coro: Coroutine[object, object, SubmitResult]) -> SubmitResult:
    """Run a coroutine, handling already-running event loops gracefully.

    - If no event loop is running, use asyncio.run (normal path).
    - If an event loop is running (e.g., Jupyter, pytest-asyncio), run the
      coroutine in a dedicated thread with its own loop to avoid
      RuntimeError about nested event loops. This will block the caller,
      so async callers should prefer submit_async().
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, SubmitResult | BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - propagate original error
            result["error"] = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    error = result.get("error")
    if isinstance(error, BaseException):
        raise error
    value = result.get("value")
    if not isinstance(value, SubmitResult):
        raise RuntimeError("submit coroutine did not produce a result")
    return value


async def submit_async(
    strategy_cls: type["Strategy"] | "Strategy",
    *,
    world: str | None = None,
    mode: Mode | str = Mode.BACKTEST,
    preset: str | None = None,
    preset_mode: str | None = None,
    preset_version: str | None = None,
    preset_overrides: dict[str, float] | None = None,
    data_preset: str | None = None,
    returns: Sequence[float] | None = None,
    auto_returns: bool | AutoReturnsConfig | None = None,
    auto_validate: bool = True,
) -> SubmitResult:
    """Submit a strategy for evaluation and potential activation.
    
    This is the single entry point for all strategy submissions in QMTL v2.0.
    The system automatically:
    1. Registers the strategy DAG
    2. Runs backtest validation
    3. Calculates performance metrics
    4. Validates against policy thresholds
    5. Activates valid strategies with appropriate weight
    
    Parameters
    ----------
    strategy_cls : type[Strategy]
        Strategy class to submit.
    world : str, optional
        Target world for the strategy. Uses QMTL_DEFAULT_WORLD env var
        or "__default__" if not specified.
    mode : Mode | str
        Execution mode: "backtest", "paper", or "live".
        Default is "backtest" for validation.
    preset : str, optional
        Policy preset to use for validation (sandbox/conservative/moderate/aggressive).
        Uses QMTL_DEFAULT_PRESET env var or "sandbox" if not specified.
    preset_mode : str, optional
        How to apply preset policy on the world (shared|clone|extend). Metadata only.
    preset_version : str, optional
        Optional preset version identifier stored with the policy.
    preset_overrides : dict[str, float], optional
        Override preset thresholds (keys like "max_drawdown.max": 0.15).
    data_preset : str, optional
        World data preset id (from world.data.presets[].id) to use for Seamless auto-wiring.
        Defaults to the first entry declared on the world.
    returns : Sequence[float], optional
        Pre-computed backtest returns for validation. If not provided,
        the system will attempt to extract returns from strategy execution.
    auto_returns : bool | AutoReturnsConfig | None
        Opt-in derivation of returns from available price/equity data. When
        enabled, the SDK will try to compute percentage returns from common
        price attributes if explicit returns are missing.
    auto_validate : bool
        Whether to run automatic validation pipeline. Default True.
    
    Returns
    -------
    SubmitResult
        Result containing strategy_id, status, metrics, and contribution info.
    
    Examples
    --------
    >>> result = await Runner.submit_async(MyStrategy)
    >>> print(result.status)  # "active" or "rejected"
    >>> print(result.contribution)  # 0.023 (2.3% contribution)
    >>> print(result.metrics.sharpe)  # 1.85
    
    >>> result = await Runner.submit_async(MyStrategy, world="prod", mode="live")
    >>> for hint in result.improvement_hints:
    ...     print(hint)
    """
    mode = _normalize_mode_value(mode)
    resolved_world = _normalize_world_id(world or _get_default_world())
    resolved_preset = preset or _get_default_preset()
    gateway_url = _get_gateway_url(resolved_world)
    execution_domain = mode_to_execution_domain(mode)
    services = get_global_services()
    strategy, strategy_class_name = _strategy_from_input(strategy_cls)
    world_ctx: WorldContext | None = None
    gateway_available = False

    from qmtl.foundation.common.compute_key import ComputeContext
    compute_context = ComputeContext(
        world_id=resolved_world,
        execution_domain=execution_domain,
    )
    def _attach_context_flags(result: SubmitResult) -> SubmitResult:
        result.downgraded = bool(getattr(compute_context, "downgraded", False))
        reason = getattr(compute_context, "downgrade_reason", None)
        result.downgrade_reason = getattr(reason, "value", reason)
        result.safe_mode = bool(getattr(compute_context, "safe_mode", False))
        return result
    setattr(strategy, "compute_context", {
        "world_id": resolved_world,
        "mode": mode.value,
    })

    async def _finalize_with_allocation(result: SubmitResult) -> SubmitResult:
        finalized = _attach_context_flags(result)
        allocation_result = AllocationSnapshotResult(snapshot=None)
        if gateway_available:
            try:
                allocation_result = await _fetch_allocation_snapshot_with_notice(
                    gateway_url=gateway_url,
                    world_id=resolved_world,
                    client=services.gateway_client,
                )
            except Exception:
                logger.debug("Failed to attach allocation snapshot", exc_info=True)
                allocation_result = AllocationSnapshotResult(
                    snapshot=None,
                    notice="allocation lookup failed (gateway error)",
                )
        else:
            allocation_result = AllocationSnapshotResult(
                snapshot=None,
                notice="gateway unavailable; allocation snapshot not fetched",
            )

        if allocation_result.snapshot is not None:
            finalized.allocation = allocation_result.snapshot
        if allocation_result.notice and not finalized.allocation_notice:
            finalized.allocation_notice = allocation_result.notice
        finalized.allocation_stale = bool(finalized.allocation_stale or allocation_result.stale)
        return finalized

    try:
        strategy.on_start()
        gateway_available = await _check_gateway_available(gateway_url, client=services.gateway_client)
        world_ctx = await _build_world_context(
            gateway_available=gateway_available,
            gateway_url=gateway_url,
            resolved_world=resolved_world,
            resolved_preset=resolved_preset,
            preset_mode=preset_mode,
            preset_version=preset_version,
            preset_overrides=preset_overrides,
            services=services,
        )
        data_notices, _ = await _maybe_configure_world_data(
            strategy=strategy,
            world_ctx=world_ctx,
            world_id=resolved_world,
            data_preset=data_preset,
            gateway_available=gateway_available,
            gateway_url=gateway_url,
            services=services,
        )
        world_ctx.world_notice.extend(data_notices)
        bootstrap_out = await _bootstrap_strategy(
            services=services,
            strategy=strategy,
            strategy_class_name=strategy_class_name,
            compute_context=compute_context,
            resolved_world=resolved_world,
            gateway_url=gateway_url,
            mode=mode,
            gateway_available=gateway_available,
            policy_payload=world_ctx.policy_payload,
        )
        backtest_returns, auto_returns_hints = await _warmup_and_collect_returns(
            services=services,
            strategy=strategy,
            gateway_available=gateway_available,
            returns=returns,
            auto_returns=auto_returns,
        )
        if not auto_validate:
            return await _finalize_with_allocation(
                _basic_result(
                    strategy=strategy,
                    strategy_id=bootstrap_out.strategy_id,
                    resolved_world=resolved_world,
                    mode=mode,
                    gateway_available=gateway_available,
                    world_notice=world_ctx.world_notice,
                )
            )
        if not backtest_returns:
            return await _finalize_with_allocation(
                _reject_due_to_no_returns(
                    strategy=strategy,
                    strategy_class_name=strategy_class_name,
                    strategy_id=bootstrap_out.strategy_id,
                    resolved_world=resolved_world,
                    mode=mode,
                    world_notice=world_ctx.world_notice,
                    auto_returns_requested=bool(auto_returns),
                    auto_returns_hints=auto_returns_hints,
                )
            )

        validation_result, ws_eval = await _run_validation_and_ws_eval(
            strategy=strategy,
            strategy_id=bootstrap_out.strategy_id or strategy_class_name,
            resolved_world=resolved_world,
            resolved_preset=world_ctx.resolved_preset,
            validation_policy=world_ctx.validation_policy,
            backtest_returns=backtest_returns,
            services=services,
            gateway_url=gateway_url,
            gateway_available=gateway_available,
        )
        return await _finalize_with_allocation(
            _build_submit_result_from_validation(
                strategy=strategy,
                strategy_class_name=strategy_class_name,
                strategy_id=bootstrap_out.strategy_id,
                resolved_world=resolved_world,
                mode=mode,
                world_notice=world_ctx.world_notice,
                validation_result=validation_result,
                ws_eval=ws_eval,
                gateway_available=gateway_available,
            )
        )
    except Exception as e:  # pragma: no cover - safety net
        try:
            strategy.on_error(e)
        except Exception:
            logger.exception("strategy.on_error raised during failure handling")

        fallback_notice = world_ctx.world_notice if world_ctx else []
        fallback_id = _strategy_id_or_fallback(None, strategy, prefix="failed")
        return await _finalize_with_allocation(
            SubmitResult(
                strategy_id=fallback_id,
                status="rejected",
                world=resolved_world,
                mode=mode,
                rejection_reason=str(e),
                improvement_hints=fallback_notice + _get_improvement_hints(e),
                strategy=strategy if "strategy" in locals() else None,
            )
        )


def _normalize_mode_value(mode: Mode | str) -> Mode:
    return Mode(mode.lower()) if isinstance(mode, str) else mode


def _strategy_from_input(strategy_cls: type["Strategy"] | "Strategy") -> tuple["Strategy", str]:
    if isinstance(strategy_cls, type):
        strategy = _prepare_strategy(strategy_cls)
        return strategy, strategy_cls.__name__
    return strategy_cls, type(strategy_cls).__name__


@dataclass
class WorldContext:
    policy_payload: dict[str, Any] | None
    resolved_preset: str | None
    world_notice: list[str]
    world_description: dict[str, Any] | None
    validation_policy: Any | None
    data_preset: str | None = None
    world_data_preset_id: str | None = None


@dataclass
class BootstrapOutcome:
    strategy_id: str | None
    offline_mode: bool


def _strategy_needs_data_provider(strategy: "Strategy") -> bool:
    try:
        from qmtl.runtime.sdk import StreamInput
    except Exception:
        return False
    return any(
        isinstance(node, StreamInput) and getattr(node, "history_provider", None) is None
        for node in getattr(strategy, "nodes", [])
    )


async def _maybe_configure_world_data(
    *,
    strategy: "Strategy",
    world_ctx: WorldContext,
    world_id: str,
    data_preset: str | None,
    gateway_available: bool,
    gateway_url: str,
    services: "RunnerServices",
) -> tuple[list[str], WorldDataSelection | None]:
    if not _strategy_needs_data_provider(strategy):
        return [], None

    world_description = world_ctx.world_description
    if world_description is None and gateway_available:
        world_description = await _fetch_world_description(
            gateway_url, world_id, client=services.gateway_client
        )
        world_ctx.world_description = world_description

    selection = resolve_world_data_selection(
        world_description=world_description,
        world_id=world_id,
        data_preset_id=data_preset,
        seamless_config=None,
    )
    if selection is None:
        raise ValueError(
            f"world '{world_id}' must define data.presets for StreamInput auto-wiring"
        )

    binding = build_provider_binding(selection)
    attached = apply_data_binding(binding, strategy=strategy, world_id=world_id)
    world_ctx.data_preset = selection.spec.key
    world_ctx.world_data_preset_id = selection.world_preset_id

    notice_source = selection.source or "packaged presets"
    return [
        (
            f"World '{world_id}' data preset '{selection.world_preset_id}' → "
            f"'{selection.data_preset_key}' applied to {attached} stream(s) "
            f"(source: {notice_source})"
        )
    ], selection


async def _build_world_context(
    *,
    gateway_available: bool,
    gateway_url: str,
    resolved_world: str,
    resolved_preset: str | None,
    preset_mode: str | None,
    preset_version: str | None,
    preset_overrides: dict[str, float] | None,
    services: "RunnerServices",
) -> WorldContext:
    overrides = preset_overrides or {}
    world_description = await _maybe_fetch_world_description(
        gateway_available=gateway_available,
        gateway_url=gateway_url,
        resolved_world=resolved_world,
        services=services,
    )
    policy_payload, world_notice = _policy_from_user_inputs(
        resolved_world=resolved_world,
        resolved_preset=resolved_preset,
        preset_mode=preset_mode,
        preset_version=preset_version,
        overrides=overrides,
    )
    resolved_preset_out = resolved_preset

    if policy_payload is None and world_description:
        policy_payload, resolved_preset_out, notice = _policy_from_world_description(
            resolved_world=resolved_world,
            world_description=world_description,
            resolved_preset=resolved_preset_out,
        )
        world_notice.extend(notice)

    if policy_payload is None and resolved_world == DEFAULT_WORLD:
        policy_payload, notice = _default_world_policy(
            resolved_preset_out=resolved_preset_out,
            preset_mode=preset_mode,
            preset_version=preset_version,
            overrides=overrides,
        )
        world_notice.extend(notice)

    if policy_payload is None and resolved_preset_out:
        policy_payload = _policy_payload_from_preset(
            preset_name=resolved_preset_out,
            preset_mode=preset_mode,
            preset_version=preset_version,
            preset_overrides=overrides,
        )

    validation_policy = _policy_from_payload(policy_payload)
    return WorldContext(
        policy_payload=policy_payload,
        resolved_preset=resolved_preset_out,
        world_notice=world_notice,
        world_description=world_description,
        validation_policy=validation_policy,
    )


async def _maybe_fetch_world_description(
    *,
    gateway_available: bool,
    gateway_url: str,
    resolved_world: str,
    services: "RunnerServices",
) -> dict[str, Any] | None:
    if not gateway_available:
        return None
    return await _fetch_world_description(gateway_url, resolved_world, client=services.gateway_client)


def _policy_from_user_inputs(
    *,
    resolved_world: str,
    resolved_preset: str | None,
    preset_mode: str | None,
    preset_version: str | None,
    overrides: dict[str, float],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not any([resolved_preset, overrides, preset_mode, preset_version]) or not resolved_preset:
        return None, []
    policy_payload = _policy_payload_from_preset(
        preset_name=resolved_preset,
        preset_mode=preset_mode,
        preset_version=preset_version,
        preset_overrides=overrides,
    )
    if not policy_payload:
        return None, []
    policy_text = _policy_to_human_readable(policy_payload)
    notice = [f"Using world '{resolved_world}' with preset '{policy_payload['preset']}' policy: {policy_text}"]
    return policy_payload, notice


def _policy_from_world_description(
    *,
    resolved_world: str,
    world_description: dict[str, Any] | None,
    resolved_preset: str | None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    if not isinstance(world_description, dict):
        return None, resolved_preset, []
    policy_payload = world_description.get("policy")
    resolved_preset_out = world_description.get("policy_preset") or resolved_preset
    human = world_description.get("policy_human") or _policy_to_human_readable(policy_payload)
    return policy_payload, resolved_preset_out, [f"World '{resolved_world}' policy: {human}"]


def _default_world_policy(
    *,
    resolved_preset_out: str | None,
    preset_mode: str | None,
    preset_version: str | None,
    overrides: dict[str, float],
) -> tuple[dict[str, Any] | None, list[str]]:
    payload = _policy_payload_from_preset(
        preset_name=resolved_preset_out or DEFAULT_PRESET,
        preset_mode=preset_mode,
        preset_version=preset_version,
        preset_overrides=overrides,
    )
    if not payload:
        return None, []
    policy_text = _policy_to_human_readable(payload)
    notice = [
        "Using default world '__default__' with '" + payload["preset"] + f"' preset: {policy_text}. "
        "Set QMTL_DEFAULT_WORLD to target a custom world or use --preset to override."
    ]
    logger.info(
        "Using default world '__default__' with '%s' preset: %s",
        payload["preset"],
        policy_text,
    )
    return payload, notice


def _policy_payload_from_preset(
    *,
    preset_name: str | None,
    preset_mode: str | None,
    preset_version: str | None,
    preset_overrides: dict[str, float],
) -> dict[str, Any] | None:
    if not preset_name:
        return None
    try:
        from .presets import get_preset

        preset_obj = get_preset(preset_name)
        payload: dict[str, Any] = {
            "preset": preset_obj.name,
            "policy": preset_obj.to_policy_dict(),
        }
        if preset_mode:
            payload["preset_mode"] = preset_mode
        if preset_version:
            payload["preset_version"] = preset_version
        if preset_overrides:
            payload["preset_overrides"] = preset_overrides
        return payload
    except Exception as exc:  # pragma: no cover - defensive, logged for observability
        logger.debug("Failed to load preset %s: %s", preset_name, exc)
        return None


async def _bootstrap_strategy(
    *,
    services: "RunnerServices",
    strategy: "Strategy",
    strategy_class_name: str,
    compute_context: Any,
    resolved_world: str,
    gateway_url: str,
    mode: Mode,
    gateway_available: bool,
    policy_payload: dict[str, Any] | None,
) -> BootstrapOutcome:
    if not gateway_available:
        logger.info("Gateway not available at %s, running local validation", gateway_url)
        return BootstrapOutcome(strategy_id=f"local_{strategy_class_name}_{id(strategy)}", offline_mode=True)

    if policy_payload is not None:
        await _ensure_world_policy(
            gateway_url=gateway_url,
            world_id=resolved_world,
            payload=policy_payload,
            client=services.gateway_client,
        )

    from .strategy_bootstrapper import StrategyBootstrapper

    bootstrapper = StrategyBootstrapper(services.gateway_client)
    bootstrap_result = await bootstrapper.bootstrap(
        strategy,
        context=compute_context,
        world_id=resolved_world,
        gateway_url=gateway_url,
        meta={"mode": mode.value},
        offline=False,
        kafka_available=services.kafka_factory.available,
        trade_mode="simulate" if mode != Mode.LIVE else "live",
        schema_enforcement="fail",
        feature_plane=services.feature_plane,
        gateway_context=None,
        skip_gateway_submission=False,
    )

    if mode != Mode.BACKTEST and not bootstrap_result.offline_mode:
        await _configure_activation(
            services=services,
            strategy_id=bootstrap_result.strategy_id,
            gateway_url=gateway_url,
            world_id=resolved_world,
            offline_mode=bootstrap_result.offline_mode,
        )

    return BootstrapOutcome(strategy_id=bootstrap_result.strategy_id, offline_mode=bootstrap_result.offline_mode)


async def _warmup_and_collect_returns(
    *,
    services: "RunnerServices",
    strategy: "Strategy",
    gateway_available: bool,
    returns: Sequence[float] | None,
    auto_returns: bool | AutoReturnsConfig | None,
) -> tuple[list[float], list[str]]:
    history_service = services.history_service
    await history_service.warmup_strategy(
        strategy,
        offline_mode=not gateway_available,
        history_start=None,
        history_end=None,
    )
    history_service.write_snapshots(strategy)
    strategy.on_finish()

    if returns is not None:
        return list(returns), []

    extracted = _extract_returns_from_strategy(strategy)
    if extracted:
        return extracted, []

    return _derive_returns_with_auto(strategy, auto_returns)


def _basic_result(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    gateway_available: bool,
    world_notice: list[str],
) -> SubmitResult:
    return SubmitResult(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy),
        status="pending" if not gateway_available else "active",
        world=resolved_world,
        mode=mode,
        contribution=None,
        weight=None,
        rank=None,
        metrics=StrategyMetrics(),
        strategy=strategy,
        improvement_hints=world_notice,
    )


def _reject_due_to_no_returns(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    auto_returns_requested: bool,
    auto_returns_hints: Sequence[str] | None = None,
) -> SubmitResult:
    logger.warning("Strategy %s produced no returns; auto-validation cannot proceed", strategy_class_name)
    improvement_hints = world_notice + [
        "Ensure your strategy populates returns/equity/pnl during warmup",
        "Pass pre-computed returns via Runner.submit(..., returns=...)",
        "Verify history data is available for the selected world/mode",
    ]
    if auto_returns_requested:
        improvement_hints.append(
            "auto_returns was enabled but derivation failed; expose a price/equity series or supply explicit returns",
        )
        if auto_returns_hints:
            improvement_hints.extend(auto_returns_hints)
    return SubmitResult(
        strategy_id=strategy_id or f"no_returns_{id(strategy)}",
        status="rejected",
        world=resolved_world,
        mode=mode,
        rejection_reason=(
            "No returns produced for validation; provide pre-computed "
            "returns or ensure the strategy populates returns/equity/pnl."
        ),
        improvement_hints=improvement_hints,
        metrics=StrategyMetrics(),
        strategy=strategy,
    )


async def _run_validation_and_ws_eval(
    *,
    strategy: "Strategy",
    strategy_id: str,
    resolved_world: str,
    resolved_preset: str | None,
    validation_policy: Any | None,
    backtest_returns: Sequence[float],
    services: "RunnerServices",
    gateway_url: str,
    gateway_available: bool,
) -> tuple[Any, WsEvalResult | None]:
    from .validation_pipeline import ValidationPipeline

    validation_pipeline = ValidationPipeline(
        preset=resolved_preset,
        policy=validation_policy,
        world_id=resolved_world,
    )
    validation_result = await validation_pipeline.validate(strategy, returns=backtest_returns)

    if not gateway_available:
        return validation_result, None

    eval_metrics = StrategyMetrics(
        sharpe=validation_result.metrics.sharpe,
        max_drawdown=validation_result.metrics.max_drawdown,
        win_rate=validation_result.metrics.win_ratio,
        profit_factor=validation_result.metrics.profit_factor,
    )
    ws_eval = await _evaluate_with_worldservice(
        gateway_url=gateway_url,
        world_id=resolved_world,
        strategy_id=strategy_id,
        metrics=eval_metrics,
        returns=backtest_returns,
        preset=resolved_preset,
        client=services.gateway_client,
    )
    if ws_eval.error:
        logger.debug("WorldService evaluation fallback error: %s", ws_eval.error)
    try:
        ws_eval.decision = await _fetch_decision_envelope(
            gateway_url=gateway_url,
            world_id=resolved_world,
        )
        ws_eval.activation = await _fetch_activation_envelope(
            gateway_url=gateway_url,
            world_id=resolved_world,
            strategy_id=strategy_id,
        )
        allocation_result = await _fetch_allocation_snapshot_with_notice(
            gateway_url=gateway_url,
            world_id=resolved_world,
            client=services.gateway_client,
        )
        ws_eval.allocation = allocation_result.snapshot
        ws_eval.allocation_notice = allocation_result.notice
        ws_eval.allocation_stale = allocation_result.stale
    except Exception:
        logger.debug("Failed to fetch WS envelopes after evaluation", exc_info=True)

    return validation_result, ws_eval


def _build_submit_result_from_validation(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: WsEvalResult | None,
    gateway_available: bool,
) -> SubmitResult:
    from .validation_pipeline import ValidationStatus

    if validation_result.status == ValidationStatus.PASSED:
        return _build_passed_result(
            strategy=strategy,
            strategy_id=strategy_id,
            resolved_world=resolved_world,
            mode=mode,
            world_notice=world_notice,
            validation_result=validation_result,
            ws_eval=ws_eval,
        )
    if validation_result.status == ValidationStatus.FAILED:
        return _build_failed_result(
            strategy=strategy,
            strategy_class_name=strategy_class_name,
            strategy_id=strategy_id,
            resolved_world=resolved_world,
            mode=mode,
            world_notice=world_notice,
            validation_result=validation_result,
            ws_eval=ws_eval,
            gateway_available=gateway_available,
        )
    return _build_error_result(
        strategy=strategy,
        strategy_id=strategy_id,
        resolved_world=resolved_world,
        mode=mode,
        world_notice=world_notice,
        validation_result=validation_result,
    )


def _build_passed_result(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: WsEvalResult | None,
) -> SubmitResult:
    precheck = _precheck_from_validation(validation_result)
    rejection = _ws_rejection_result(
        strategy=strategy,
        strategy_id=strategy_id,
        resolved_world=resolved_world,
        mode=mode,
        world_notice=world_notice,
        validation_result=validation_result,
        ws_eval=ws_eval,
    )
    if rejection:
        rejection.precheck = precheck
        return rejection

    status = _resolved_status(validation_result, ws_eval)
    weight = None if ws_eval else validation_result.weight
    rank = None if ws_eval else validation_result.rank
    contribution = None if ws_eval else validation_result.contribution
    weight, rank, contribution = _merge_ws_eval_fields(ws_eval, weight, rank, contribution)
    metrics_out = _base_metrics_from_validation(validation_result)
    if ws_eval and ws_eval.correlation_avg is not None:
        metrics_out = _clone_metrics_with_corr(metrics_out, ws_eval.correlation_avg)

    return SubmitResult(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy),
        status=status,
        world=resolved_world,
        mode=mode,
        contribution=contribution,
        weight=weight,
        rank=rank,
        metrics=metrics_out,
        strategy=strategy,
        improvement_hints=world_notice + validation_result.improvement_hints,
        precheck=precheck,
        decision=ws_eval.decision if ws_eval else None,
        activation=ws_eval.activation if ws_eval else None,
        allocation=ws_eval.allocation if ws_eval else None,
        allocation_notice=ws_eval.allocation_notice if ws_eval else None,
        allocation_stale=ws_eval.allocation_stale if ws_eval else False,
    )


def _ws_rejection_result(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: WsEvalResult | None,
) -> SubmitResult | None:
    if ws_eval is None:
        return None
    has_rejection = ws_eval.active is False or (ws_eval.violations and len(ws_eval.violations) > 0)
    if not has_rejection:
        return None
    ws_reject_violations = _final_threshold_violations(validation_result, ws_eval)
    return SubmitResult(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="rejected"),
        status="rejected",
        world=resolved_world,
        mode=mode,
        rejection_reason="WorldService evaluation rejected strategy",
        improvement_hints=world_notice + validation_result.improvement_hints,
        threshold_violations=ws_reject_violations,
        metrics=_base_metrics_from_validation(validation_result),
        strategy=strategy,
        precheck=_precheck_from_validation(validation_result),
        decision=ws_eval.decision,
        activation=ws_eval.activation,
        allocation=ws_eval.allocation,
        allocation_notice=ws_eval.allocation_notice,
        allocation_stale=ws_eval.allocation_stale,
    )


def _resolved_status(validation_result: Any, ws_eval: WsEvalResult | None) -> str:
    if ws_eval:
        if ws_eval.active is True:
            return "active"
        if ws_eval.active is False:
            return "rejected"
        if ws_eval.error:
            return "pending"
    if getattr(validation_result, "activated", False):
        return "active"
    from .validation_pipeline import ValidationStatus
    if getattr(validation_result, "status", None) == ValidationStatus.PASSED:
        return "validated"
    if getattr(validation_result, "status", None) == ValidationStatus.FAILED:
        return "rejected"
    return "pending"


def _merge_ws_eval_fields(
    ws_eval: WsEvalResult | None,
    weight: float | None,
    rank: int | None,
    contribution: float | None,
) -> tuple[float | None, int | None, float | None]:
    if ws_eval:
        weight = ws_eval.weight
        rank = ws_eval.rank
        contribution = ws_eval.contribution
    return weight, rank, contribution


def _build_failed_result(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: WsEvalResult | None,
    gateway_available: bool,
) -> SubmitResult:
    if gateway_available and ws_eval and ws_eval.active is True:
        return _ws_accepts_after_fail(
            strategy=strategy,
            strategy_class_name=strategy_class_name,
            strategy_id=strategy_id,
            resolved_world=resolved_world,
            mode=mode,
            world_notice=world_notice,
            validation_result=validation_result,
            ws_eval=ws_eval,
        )

    if gateway_available and (ws_eval is None or ws_eval.error):
        return _pending_after_failed_validation(
            strategy=strategy,
            strategy_class_name=strategy_class_name,
            strategy_id=strategy_id,
            resolved_world=resolved_world,
            mode=mode,
            world_notice=world_notice,
            validation_result=validation_result,
            ws_eval=ws_eval,
        )

    return _reject_after_failed_validation(
        strategy=strategy,
        strategy_id=strategy_id,
        resolved_world=resolved_world,
        mode=mode,
        world_notice=world_notice,
        validation_result=validation_result,
        ws_eval=ws_eval,
    )


def _ws_accepts_after_fail(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: WsEvalResult,
) -> SubmitResult:
    logger.info(
        "Local validation failed but WorldService accepted strategy %s; deferring to WS decision",
        strategy_id or strategy_class_name,
    )
    for v in validation_result.violations:
        logger.warning(
            "Local validation warning (overridden by WS): %s=%s (threshold %s %s)",
            v.metric, v.value, v.threshold_type, v.threshold_value,
        )
    metrics_out = _clone_metrics_with_corr(_base_metrics_from_validation(validation_result), ws_eval.correlation_avg)
    return SubmitResult(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="ws_accepted"),
        status="active",
        world=resolved_world,
        mode=mode,
        contribution=ws_eval.contribution,
        weight=ws_eval.weight,
        rank=ws_eval.rank,
        metrics=metrics_out,
        strategy=strategy,
        improvement_hints=world_notice + [
            "Note: Local validation failed but WorldService accepted with world-aware metrics"
        ] + validation_result.improvement_hints,
        precheck=_precheck_from_validation(validation_result),
        decision=ws_eval.decision,
        activation=ws_eval.activation,
        allocation=ws_eval.allocation,
        allocation_notice=ws_eval.allocation_notice,
        allocation_stale=ws_eval.allocation_stale,
    )


def _pending_after_failed_validation(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: WsEvalResult | None,
) -> SubmitResult:
    ws_error_msg = ws_eval.error if ws_eval else "WS evaluation unavailable"
    logger.warning(
        "Local validation failed for %s but WS evaluation also failed (%s); deferring with pending status",
        strategy_id or strategy_class_name,
        ws_error_msg,
    )
    for v in validation_result.violations:
        logger.warning(
            "Local validation warning (WS unavailable): %s=%s (threshold %s %s)",
            v.metric, v.value, v.threshold_type, v.threshold_value,
        )
    return SubmitResult(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="pending"),
        status="pending",
        world=resolved_world,
        mode=mode,
        metrics=StrategyMetrics(
            sharpe=validation_result.metrics.sharpe,
        max_drawdown=validation_result.metrics.max_drawdown,
        win_rate=validation_result.metrics.win_ratio,
        profit_factor=validation_result.metrics.profit_factor,
        ) if ws_eval else _base_metrics_from_validation(validation_result),
        strategy=strategy,
        improvement_hints=world_notice + [
            f"Local validation failed but WS evaluation unavailable ({ws_error_msg}); strategy submitted as pending "
            "for server-side evaluation"
        ] + validation_result.improvement_hints,
        threshold_violations=_final_threshold_violations(validation_result, ws_eval),
        precheck=_precheck_from_validation(validation_result),
        decision=ws_eval.decision if ws_eval else None,
        activation=ws_eval.activation if ws_eval else None,
        allocation=ws_eval.allocation if ws_eval else None,
        allocation_notice=ws_eval.allocation_notice if ws_eval else None,
        allocation_stale=ws_eval.allocation_stale if ws_eval else False,
    )


def _reject_after_failed_validation(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: WsEvalResult | None,
) -> SubmitResult:
    rejection_reason, ws_extra_violations = _rejection_details(ws_eval, validation_result)
    final_thresholds = ws_extra_violations if ws_extra_violations else _final_threshold_violations(validation_result, ws_eval)

    return SubmitResult(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="rejected"),
        status="rejected",
        world=resolved_world,
        mode=mode,
        rejection_reason=rejection_reason,
        improvement_hints=world_notice + validation_result.improvement_hints,
        threshold_violations=final_thresholds,
        metrics=StrategyMetrics(
            sharpe=validation_result.metrics.sharpe,
            max_drawdown=validation_result.metrics.max_drawdown,
            win_rate=validation_result.metrics.win_ratio,
            profit_factor=validation_result.metrics.profit_factor,
        ),
        strategy=strategy,
        precheck=_precheck_from_validation(validation_result),
        decision=ws_eval.decision if ws_eval else None,
        activation=ws_eval.activation if ws_eval else None,
        allocation=ws_eval.allocation if ws_eval else None,
        allocation_notice=ws_eval.allocation_notice if ws_eval else None,
        allocation_stale=ws_eval.allocation_stale if ws_eval else False,
    )


def _rejection_details(ws_eval: WsEvalResult | None, validation_result: Any) -> tuple[str, list[dict[str, object]]]:
    rejection_reason = "Strategy did not meet policy thresholds"
    if ws_eval is None:
        return rejection_reason, []

    if ws_eval.active is False:
        rejection_reason = "WorldService evaluation rejected strategy"
    if ws_eval.error:
        rejection_reason += f" (WS error: {ws_eval.error})"

    ws_extra_violations: list[dict[str, object]] = []
    if ws_eval.violations:
        validation_result.improvement_hints.extend(
            [str(ws_violation.get("message", "")) for ws_violation in ws_eval.violations if ws_violation.get("message")]
        )
        for ws_violation in ws_eval.violations:
            ws_extra_violations.append(
                {
                    "metric": ws_violation.get("metric"),
                    "value": ws_violation.get("value"),
                    "threshold_type": ws_violation.get("threshold_type") or ws_violation.get("type"),
                    "threshold_value": ws_violation.get("threshold_value") or ws_violation.get("threshold"),
                    "message": ws_violation.get("message"),
                }
            )
    return rejection_reason, ws_extra_violations


def _build_error_result(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    mode: Mode,
    world_notice: list[str],
    validation_result: Any,
) -> SubmitResult:
    return SubmitResult(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="error"),
        status="rejected",
        world=resolved_world,
        mode=mode,
        rejection_reason=validation_result.error_message or "Validation error",
        improvement_hints=world_notice + validation_result.improvement_hints,
        strategy=strategy,
        precheck=_precheck_from_validation(validation_result),
    )


def _strategy_id_or_fallback(strategy_id: str | None, strategy: "Strategy", *, prefix: str = "unknown") -> str:
    return strategy_id or f"{prefix}_{id(strategy)}"


def _base_metrics_from_validation(validation_result: Any) -> StrategyMetrics:
    return StrategyMetrics(
        sharpe=validation_result.metrics.sharpe,
        max_drawdown=validation_result.metrics.max_drawdown,
        win_rate=validation_result.metrics.win_ratio,
        profit_factor=validation_result.metrics.profit_factor,
        car_mdd=validation_result.metrics.car_mdd,
        rar_mdd=validation_result.metrics.rar_mdd,
        total_return=validation_result.metrics.total_return,
        num_trades=validation_result.metrics.num_trades,
        correlation_avg=validation_result.correlation_avg,
    )


def _validation_violations(validation_result: Any) -> list[dict[str, object]]:
    return [
        {
            "metric": v.metric,
            "value": v.value,
            "threshold_type": v.threshold_type,
            "threshold_value": v.threshold_value,
            "message": v.message,
        }
        for v in getattr(validation_result, "violations", [])
    ]


def _final_threshold_violations(validation_result: Any, ws_eval: WsEvalResult | None) -> list[dict[str, object]]:
    if ws_eval and ws_eval.violations:
        return ws_eval.violations
    return _validation_violations(validation_result)


def _precheck_from_validation(validation_result: Any) -> PrecheckResult:
    """Summarize local ValidationPipeline output for reference."""
    try:
        from .validation_pipeline import ValidationStatus
        status_value = validation_result.status.value if hasattr(validation_result, "status") else ValidationStatus.PENDING
    except Exception:
        status_value = str(getattr(validation_result, "status", "pending"))

    return PrecheckResult(
        status=str(status_value),
        activated=bool(getattr(validation_result, "activated", False)),
        weight=getattr(validation_result, "weight", None),
        rank=getattr(validation_result, "rank", None),
        contribution=getattr(validation_result, "contribution", None),
        metrics=_base_metrics_from_validation(validation_result),
        violations=_validation_violations(validation_result),
        improvement_hints=list(getattr(validation_result, "improvement_hints", [])),
        correlation_avg=getattr(validation_result, "correlation_avg", None),
    )


def _clone_metrics_with_corr(metrics: StrategyMetrics, correlation_avg: float | None) -> StrategyMetrics:
    if correlation_avg is None:
        return metrics
    return StrategyMetrics(
        sharpe=metrics.sharpe,
        max_drawdown=metrics.max_drawdown,
        correlation_avg=correlation_avg,
        win_rate=metrics.win_rate,
        profit_factor=metrics.profit_factor,
        car_mdd=metrics.car_mdd,
        rar_mdd=metrics.rar_mdd,
        total_return=metrics.total_return,
        num_trades=metrics.num_trades,
    )


def _normalize_auto_returns_config(
    auto_returns: bool | AutoReturnsConfig | None,
) -> AutoReturnsConfig | None:
    if auto_returns is None or auto_returns is False:
        return None
    if auto_returns is True:
        return AutoReturnsConfig()
    if isinstance(auto_returns, AutoReturnsConfig):
        return auto_returns
    raise TypeError("auto_returns must be a bool, AutoReturnsConfig, or None")


def _derive_returns_with_auto(
    strategy: "Strategy",
    auto_returns: bool | AutoReturnsConfig | None,
) -> tuple[list[float], list[str]]:
    config = _normalize_auto_returns_config(auto_returns)
    if config is None:
        return [], []

    prices, source_attr = _extract_price_series(strategy, config.price_attributes)
    if not prices:
        searched = ", ".join(config.price_attributes)
        return [], [
            (
                "auto_returns enabled but no price/equity series was found; "
                f"set one of [{searched}] or provide explicit returns"
            )
        ]

    if len(prices) < config.min_length:
        return [], [
            (
                "auto_returns price series too short to derive returns; "
                f"expected at least {config.min_length} points from `{source_attr}`"
            )
        ]

    try:
        return _pct_change(prices), []
    except ValueError as exc:  # pragma: no cover - defensive path
        return [], [f"auto_returns failed using `{source_attr}`: {exc}"]


def _extract_price_series(
    strategy: "Strategy", price_attributes: Sequence[str]
) -> tuple[list[SupportsFloat], str | None]:
    for attr in price_attributes:
        candidate = getattr(strategy, attr, None)
        if candidate is None or isinstance(candidate, str):
            continue
        try:
            series = list(candidate)
        except Exception:
            continue
        if not series:
            continue
        return series, attr
    return [], None


def _pct_change(values: Sequence[SupportsFloat]) -> list[float]:
    returns: list[float] = []
    for idx in range(1, len(values)):
        prev, curr = values[idx - 1], values[idx]
        if not _is_finite_number(prev) or not _is_finite_number(curr):
            raise ValueError("non-finite price encountered while deriving returns")
        prev_float = float(prev)
        curr_float = float(curr)
        if prev_float == 0:
            raise ValueError("encountered zero price while deriving returns")
        returns.append((curr_float - prev_float) / prev_float)
    return returns


def _is_finite_number(value: numbers.Real | SupportsFloat) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _extract_returns_from_strategy(strategy: "Strategy") -> list[float]:
    """Extract returns from a strategy instance if available."""
    returns_attr = getattr(strategy, "returns", None)
    if returns_attr:
        return list(returns_attr)

    equity_attr = getattr(strategy, "equity", None)
    if equity_attr:
        equity = list(equity_attr)
        if len(equity) >= 2:
            returns = []
            for i in range(1, len(equity)):
                if equity[i - 1] != 0:
                    returns.append((equity[i] - equity[i - 1]) / equity[i - 1])
                else:
                    returns.append(0.0)
            return returns

    pnl_attr = getattr(strategy, "pnl", None)
    if pnl_attr:
        return list(pnl_attr)

    return []


def _prepare_strategy(strategy_cls: type["Strategy"]) -> "Strategy":
    """Instantiate and set up a Strategy."""
    strategy = strategy_cls()
    strategy.setup()
    return strategy


async def _configure_activation(
    *,
    services: "RunnerServices",
    strategy_id: str | None,
    gateway_url: str | None,
    world_id: str,
    offline_mode: bool,
) -> None:
    """Configure activation manager and trade dispatcher for live modes."""
    if gateway_url and not offline_mode:
        try:
            activation_manager = services.ensure_activation_manager(
                gateway_url=gateway_url,
                world_id=world_id,
                strategy_id=strategy_id,
            )
            services.trade_dispatcher.set_activation_manager(activation_manager)
            await activation_manager.start()
            return
        except Exception:
            logger.warning(
                "Activation manager failed to start; proceeding with gates OFF by default"
            )
    services.trade_dispatcher.set_activation_manager(services.activation_manager)


def submit(
    strategy_cls: type["Strategy"],
    *,
    world: str | None = None,
    mode: Mode | str = Mode.BACKTEST,
    preset: str | None = None,
    preset_mode: str | None = None,
    preset_version: str | None = None,
    preset_overrides: dict[str, float] | None = None,
    data_preset: str | None = None,
    returns: Sequence[float] | None = None,
    auto_returns: bool | AutoReturnsConfig | None = None,
    auto_validate: bool = True,
) -> SubmitResult:
    """Synchronous wrapper around submit_async.
    
    This is the primary entry point for strategy submission.
    
    Parameters
    ----------
    strategy_cls : type[Strategy]
        Strategy class to submit.
    world : str, optional
        Target world for the strategy.
    mode : Mode | str
        Execution mode: "backtest", "paper", or "live".
    preset : str, optional
        Policy preset for validation and world policy application.
    preset_mode : str, optional
        How to apply the preset world policy (shared|clone|extend). Metadata only.
    preset_version : str, optional
        Optional preset version identifier to store with world policy.
    preset_overrides : dict[str, float], optional
        Override preset thresholds (e.g., {'max_drawdown.max': 0.15}).
    data_preset : str, optional
        World data preset id (from world.data.presets[].id) to use for Seamless auto-wiring.
        Defaults to the first entry declared on the world.
    returns : Sequence[float], optional
        Pre-computed backtest returns.
    auto_returns : bool | AutoReturnsConfig | None
        Whether to derive returns from price/equity data when explicit returns
        are missing.
    auto_validate : bool
        Whether to run automatic validation. Default True.
    
    Examples
    --------
    >>> result = Runner.submit(MyStrategy)
    >>> print(result.status)
    
    >>> result = Runner.submit(MyStrategy, world="prod", mode="live")
    """
    return _run_coroutine_blocking(submit_async(
        strategy_cls,
        world=_normalize_world_id(world or _get_default_world()),
        mode=mode,
        preset=preset,
        preset_mode=preset_mode,
        preset_version=preset_version,
        preset_overrides=preset_overrides,
        data_preset=data_preset,
        returns=returns,
        auto_returns=auto_returns,
        auto_validate=auto_validate,
    ))


async def _check_gateway_available(gateway_url: str, client: "GatewayClient | None" = None) -> bool:
    """Check if gateway is available."""
    try:
        if client is not None:
            health = await client.get_health(gateway_url=gateway_url)
            return bool(health)  # Non-empty dict means healthy
        # Fallback to direct httpx if no client provided
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.get(f"{gateway_url}/health")
            return response.status_code == 200
    except Exception:
        return False


async def _fetch_world_description(
    gateway_url: str, world_id: str, client: "GatewayClient | None" = None
) -> dict[str, Any] | None:
    """Fetch world description (policy/preset metadata) from Gateway.

    Uses the /worlds/{id}/describe endpoint to get full world info including:
    - policy dict
    - policy_preset, policy_preset_mode, policy_preset_version
    - policy_human (human-readable string)
    """
    try:
        if client is not None:
            data = await client.describe_world(gateway_url=gateway_url, world_id=world_id)
            if data:
                return data
            fallback = await client.get_world(gateway_url=gateway_url, world_id=world_id)
            if fallback:
                return fallback
        # Fallback to direct httpx if no client provided
        base_url = gateway_url.rstrip("/")
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(f"{base_url}/worlds/{world_id}/describe")
            if resp.status_code == 404:
                resp_world = await http_client.get(f"{base_url}/worlds/{world_id}")
                if resp_world.status_code == 404:
                    return None
                resp_world.raise_for_status()
                raw_world = resp_world.json()
                return raw_world if isinstance(raw_world, dict) else None
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
    except Exception:
        logger.debug("Failed to fetch world description for %s", world_id, exc_info=True)
        return None


def _policy_from_payload(payload: dict[str, Any] | None) -> Any | None:
    """Extract Policy model from world payload or preset dict."""
    if payload is None:
        return None
    try:
        from qmtl.services.worldservice.policy_engine import Policy
    except Exception:
        return None

    base = payload
    if isinstance(payload, dict) and "policy" in payload and isinstance(payload["policy"], dict):
        base = payload["policy"]
    try:
        return Policy.model_validate(base)
    except Exception:
        logger.debug("Failed to parse policy payload for validation", exc_info=True)
        return None


async def _ensure_world_policy(
    *,
    gateway_url: str,
    world_id: str,
    payload: dict[str, Any],
    client: "GatewayClient | None" = None,
) -> None:
    """Ensure a world exists and apply the given policy payload."""
    if client is not None:
        await client.ensure_world_with_policy(
            gateway_url=gateway_url,
            world_id=world_id,
            policy_payload=payload,
        )
        return

    # Fallback to direct httpx if no client provided
    base_url = gateway_url.rstrip("/")
    normalized_payload = dict(payload)
    if "overrides" in normalized_payload and "preset_overrides" not in normalized_payload:
        normalized_payload["preset_overrides"] = normalized_payload.pop("overrides")
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(f"{base_url}/worlds/{world_id}")
            if resp.status_code == 404:
                await http_client.post(
                    f"{base_url}/worlds",
                    json={"id": world_id, "name": world_id},
                )
            await http_client.post(
                f"{base_url}/worlds/{world_id}/policies",
                json=normalized_payload,
            )
    except Exception:  # pragma: no cover - network/JSON issues
        logger.debug("Failed to ensure world %s at %s", world_id, base_url, exc_info=True)


def _get_improvement_hints(error: Exception) -> list[str]:
    """Generate improvement hints based on error type."""
    hints = []
    error_str = str(error).lower()
    
    if "validation" in error_str:
        hints.append("Check that all nodes have valid intervals and periods")
    if "connection" in error_str or "network" in error_str:
        hints.append("Ensure gateway is running and QMTL_GATEWAY_URL is set correctly")
    if "schema" in error_str:
        hints.append("Verify node input/output schemas match expected types")
    if "history" in error_str or "data" in error_str:
        hints.append("Check that history data is available for the requested period")
    
    if not hints:
        hints.append("Review the error message and check strategy implementation")
    
    return hints


@dataclass
class WsEvalResult:
    active: bool | None = None
    weight: float | None = None
    rank: int | None = None
    contribution: float | None = None
    violations: list[dict[str, object]] | None = None
    correlation_avg: float | None = None
    error: str | None = None
    decision: DecisionEnvelope | None = None
    activation: ActivationEnvelope | None = None
    allocation: AllocationSnapshot | None = None
    allocation_notice: str | None = None
    allocation_stale: bool = False


async def _evaluate_with_worldservice(
    *,
    gateway_url: str,
    world_id: str,
    strategy_id: str,
    metrics: "StrategyMetrics",
    returns: Sequence[float],
    preset: str | None,
    client: "GatewayClient | None" = None,
) -> WsEvalResult:
    """Ask WorldService (via Gateway) to evaluate strategy metrics."""
    payload_metrics: dict[str, float] = {}
    # StrategyMetrics lacks drawdown sign convention; map to common keys
    for key in ("sharpe", "max_drawdown", "win_rate", "win_ratio", "profit_factor"):
        value = getattr(metrics, key, None)
        if value is not None:
            payload_metrics[key] = float(value)
    policy_payload: dict[str, Any] | None = None
    if preset:
        try:
            from .presets import get_preset
            preset_obj = get_preset(preset)
            policy_dict = preset_obj.to_policy_dict()
            policy_payload = {"name": preset_obj.name, **policy_dict}
        except Exception:
            policy_payload = None

    # Use GatewayClient if provided
    if client is not None:
        data = await client.evaluate_strategy(
            gateway_url=gateway_url,
            world_id=world_id,
            strategy_id=strategy_id,
            metrics=payload_metrics,
            returns=list(returns),
            policy_payload=policy_payload,
        )
        if "error" in data:
            return WsEvalResult(error=str(data["error"]))
        return _parse_ws_eval_response(data, strategy_id)

    # Fallback to direct httpx
    payload: dict[str, Any] = {
        "metrics": {strategy_id: payload_metrics},
        "series": {strategy_id: {"returns": list(returns)}},
    }
    if policy_payload:
        payload["policy"] = policy_payload
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.post(
                f"{gateway_url.rstrip('/')}/worlds/{world_id}/evaluate",
                json=payload,
            )
            if resp.status_code >= 400:
                return WsEvalResult(error=f"WS evaluate error {resp.status_code}")
            data = resp.json()
            return _parse_ws_eval_response(data, strategy_id)
    except Exception as exc:  # pragma: no cover - network/JSON issues
        return WsEvalResult(error=str(exc))


async def _fetch_decision_envelope(
    *,
    gateway_url: str,
    world_id: str,
) -> DecisionEnvelope | None:
    """Fetch the latest DecisionEnvelope from WorldService."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(f"{gateway_url.rstrip('/')}/worlds/{world_id}/decide")
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict):
                return DecisionEnvelope.model_validate(payload)
    except Exception:
        logger.debug("Failed to fetch decision envelope via HTTP", exc_info=True)
    return None


async def _fetch_activation_envelope(
    *,
    gateway_url: str,
    world_id: str,
    strategy_id: str,
    side: str = "long",
) -> ActivationEnvelope | None:
    """Fetch ActivationEnvelope for the given strategy if available."""
    params = {"strategy_id": strategy_id, "side": side}
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(
                f"{gateway_url.rstrip('/')}/worlds/{world_id}/activation",
                params=params,
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict):
                return ActivationEnvelope.model_validate(payload)
    except Exception:
        logger.debug("Failed to fetch activation envelope via HTTP", exc_info=True)
    return None


def _extract_allocation_snapshot(
    payload: dict[str, Any] | None, world_id: str
) -> AllocationSnapshot | None:
    if not isinstance(payload, dict):
        return None
    allocations = payload.get("allocations")
    if not isinstance(allocations, dict):
        return None
    snapshot: dict[str, Any] | None = None
    for candidate in _world_id_candidates(world_id):
        candidate_snapshot = allocations.get(candidate)
        if isinstance(candidate_snapshot, dict):
            snapshot = candidate_snapshot
            break
    if snapshot is None and len(allocations) == 1:
        only_entry = next(iter(allocations.values()))
        snapshot = only_entry if isinstance(only_entry, dict) else None
    if snapshot is None:
        return None

    try:
        alloc_value_raw = snapshot.get("allocation")
        alloc_value = float(alloc_value_raw) if alloc_value_raw is not None else None
    except (TypeError, ValueError):
        alloc_value = None
    stale_raw = snapshot.get("stale")
    stale_flag = None
    if isinstance(stale_raw, bool):
        stale_flag = stale_raw
    elif stale_raw is not None:
        try:
            stale_flag = bool(int(stale_raw))
        except Exception:
            stale_flag = None

    strategy_alloc_total: dict[str, float] | None = None
    raw_strategy_alloc = snapshot.get("strategy_alloc_total")
    if isinstance(raw_strategy_alloc, dict):
        strategy_alloc_total = {}
        for sid, ratio in raw_strategy_alloc.items():
            try:
                val = float(ratio)
            except (TypeError, ValueError):
                continue
            if isfinite(val):
                strategy_alloc_total[str(sid)] = val
        if not strategy_alloc_total:
            strategy_alloc_total = None

    return AllocationSnapshot(
        world_id=str(snapshot.get("world_id") or world_id),
        allocation=alloc_value,
        run_id=str(snapshot.get("run_id")) if snapshot.get("run_id") is not None else None,
        etag=str(snapshot.get("etag")) if snapshot.get("etag") is not None else None,
        strategy_alloc_total=strategy_alloc_total,
        updated_at=str(snapshot.get("updated_at")) if snapshot.get("updated_at") is not None else None,
        stale=stale_flag,
    )


async def _fetch_allocation_snapshot(
    *,
    gateway_url: str,
    world_id: str,
    client: "GatewayClient | None",
) -> AllocationSnapshot | None:
    result = await _fetch_allocation_snapshot_with_notice(
        gateway_url=gateway_url,
        world_id=world_id,
        client=client,
    )
    return result.snapshot


async def _fetch_allocation_snapshot_with_notice(
    *,
    gateway_url: str,
    world_id: str,
    client: "GatewayClient | None",
) -> AllocationSnapshotResult:
    if client is None:
        return AllocationSnapshotResult(
            snapshot=None,
            notice="gateway client not configured",
        )
    try:
        payload = await client.get_allocations(
            gateway_url=gateway_url,
            world_id=world_id,
        )
    except Exception as exc:
        logger.debug("Failed to fetch allocation snapshot", exc_info=True)
        return AllocationSnapshotResult(snapshot=None, notice=str(exc))

    if payload is None:
        return AllocationSnapshotResult(
            snapshot=None,
            notice="gateway returned no allocation payload",
        )

    snapshot = _extract_allocation_snapshot(payload, world_id)
    if snapshot is None:
        return AllocationSnapshotResult(
            snapshot=None,
            notice=f"no allocation snapshot found for world '{world_id}'",
        )

    stale = False
    if isinstance(payload, dict):
        payload_stale = payload.get("stale")
        if isinstance(payload_stale, bool):
            stale = payload_stale
    if snapshot.stale is not None:
        stale = bool(snapshot.stale)

    return AllocationSnapshotResult(snapshot=snapshot, stale=stale)


def _parse_ws_eval_response(data: dict[str, Any], strategy_id: str) -> WsEvalResult:
    """Parse WorldService evaluation response into WsEvalResult."""
    active_list = data.get("active", [])
    weights = data.get("weights", {}) or {}
    contributions = data.get("contributions", {}) or data.get("contribution", {}) or {}
    ranks = data.get("ranks", {}) or {}
    violations = data.get("violations") or data.get("threshold_violations")
    correlation_avg = data.get("correlation_avg") or data.get("correlation")

    is_active = strategy_id in active_list if isinstance(active_list, list) else None
    weight = _value_from_mapping(weights, strategy_id)
    contribution = _value_from_mapping(contributions, strategy_id)
    rank = _value_from_mapping(ranks, strategy_id)
    violations_list = violations if isinstance(violations, list) else None
    corr = float(correlation_avg) if isinstance(correlation_avg, (int, float)) else None

    return WsEvalResult(
        active=is_active,
        weight=weight,
        contribution=contribution,
        rank=rank,
        violations=violations_list,
        correlation_avg=corr,
    )


def _value_from_mapping(mapping: object, key: str) -> Any:
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None
