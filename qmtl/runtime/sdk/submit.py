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
import os
from threading import Thread
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Coroutine, Sequence

import httpx

if TYPE_CHECKING:
    from .strategy import Strategy
    from .gateway_client import GatewayClient

from .mode import Mode, mode_to_execution_domain

logger = logging.getLogger(__name__)

# Re-export Mode for backward compatibility
__all__ = ["Mode", "SubmitResult", "StrategyMetrics", "submit", "submit_async"]


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
    
    # Contribution to world (populated after validation)
    contribution: float | None = None  # Contribution to world returns
    weight: float | None = None  # Portfolio weight
    rank: int | None = None  # Rank within world
    
    # Performance metrics
    metrics: StrategyMetrics = field(default_factory=StrategyMetrics)
    
    # Rejection info (if status == "rejected")
    rejection_reason: str | None = None
    improvement_hints: list[str] = field(default_factory=list)
    
    # Threshold violations (for rejected strategies)
    threshold_violations: list[dict] = field(default_factory=list)
    
    # Internal reference to the instantiated strategy (for debugging/tests)
    strategy: "Strategy | None" = None


# Default configuration
DEFAULT_WORLD = "__default__"
DEFAULT_GATEWAY_URL = "http://localhost:8000"
DEFAULT_PRESET = "sandbox"  # Use sandbox preset for zero-config submissions

# Environment variable names
ENV_GATEWAY_URL = "QMTL_GATEWAY_URL"
ENV_DEFAULT_WORLD = "QMTL_DEFAULT_WORLD"
ENV_DEFAULT_PRESET = "QMTL_DEFAULT_PRESET"


def _get_gateway_url() -> str:
    """Get gateway URL from environment or use default."""
    return os.environ.get(ENV_GATEWAY_URL, DEFAULT_GATEWAY_URL)


def _get_default_world() -> str:
    """Get default world from environment or use default."""
    return os.environ.get(ENV_DEFAULT_WORLD, DEFAULT_WORLD)


def _get_default_preset() -> str:
    """Get default preset from environment or use default."""
    return os.environ.get(ENV_DEFAULT_PRESET, DEFAULT_PRESET)


def _policy_to_human_readable(policy: Any) -> str:
    """Convert a policy-like dict to a concise human readable string."""
    if policy is None:
        return "no policy"
    if isinstance(policy, dict):
        data = policy.get("policy") if "policy" in policy else policy
        preset = policy.get("preset")
    else:
        try:
            data = policy.model_dump()
            preset = None
        except Exception:
            data = {}
            preset = None

    thresholds = data.get("thresholds") if isinstance(data, dict) else None
    parts: list[str] = []
    if preset:
        parts.append(f"preset={preset}")

    if isinstance(thresholds, dict):
        thresh_bits: list[str] = []
        for metric, cfg in thresholds.items():
            if not isinstance(cfg, dict):
                continue
            min_v = cfg.get("min")
            max_v = cfg.get("max")
            if min_v is not None and max_v is not None:
                thresh_bits.append(f"{metric} between {min_v} and {max_v}")
            elif min_v is not None:
                thresh_bits.append(f"{metric} >= {min_v}")
            elif max_v is not None:
                thresh_bits.append(f"{metric} <= {max_v}")
        if thresh_bits:
            parts.append("thresholds: " + "; ".join(thresh_bits))

    top_k = data.get("top_k") if isinstance(data, dict) else None
    if isinstance(top_k, dict):
        metric = top_k.get("metric")
        k = top_k.get("k")
        if metric and k:
            parts.append(f"top_k: keep top {k} by {metric}")

    corr = data.get("correlation") if isinstance(data, dict) else None
    if isinstance(corr, dict) and corr.get("max") is not None:
        parts.append(f"correlation max: {corr.get('max')}")

    hyst = data.get("hysteresis") if isinstance(data, dict) else None
    if isinstance(hyst, dict) and hyst.get("metric") and hyst.get("enter") is not None and hyst.get("exit") is not None:
        parts.append(
            f"hysteresis on {hyst['metric']}: enter {hyst['enter']}, exit {hyst['exit']}"
        )

    return ", ".join(parts) if parts else "no policy"


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

    result: dict[str, object] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001 - propagate original error
            result["error"] = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    value = result.get("value")
    if value is None:
        raise RuntimeError("submit coroutine did not produce a result")
    return value  # type: ignore[return-value]


async def submit_async(
    strategy_cls: type["Strategy"] | "Strategy",
    *,
    world: str | None = None,
    mode: Mode | str = Mode.BACKTEST,
    preset: str | None = None,
    preset_mode: str | None = None,
    preset_version: str | None = None,
    preset_overrides: dict[str, float] | None = None,
    returns: Sequence[float] | None = None,
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
    returns : Sequence[float], optional
        Pre-computed backtest returns for validation. If not provided,
        the system will attempt to extract returns from strategy execution.
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
    from .runner import Runner
    from qmtl.foundation.common.compute_key import ComputeContext
    from .validation_pipeline import ValidationPipeline, ValidationStatus
    
    # Normalize mode
    if isinstance(mode, str):
        mode = Mode(mode.lower())
    
    # Resolve world, gateway, and preset
    resolved_world = world or _get_default_world()
    resolved_preset = preset or _get_default_preset()
    gateway_url = _get_gateway_url()
    world_notice: list[str] = []
    
    # Map mode to internal execution domain
    execution_domain = mode_to_execution_domain(mode)
    
    services = Runner.services()
    
    # Handle both class and instance
    if isinstance(strategy_cls, type):
        strategy = Runner._prepare(strategy_cls)
        strategy_class_name = strategy_cls.__name__
    else:
        # Already an instance
        strategy = strategy_cls
        strategy_class_name = type(strategy).__name__
    
    # Create compute context
    compute_context = ComputeContext(
        world_id=resolved_world,
        execution_domain=execution_domain,
    )
    setattr(strategy, "compute_context", {
        "world_id": resolved_world,
        "mode": mode.value,
    })
    
    strategy_id: str | None = None
    backtest_returns: list[float] = []
    
    try:
        strategy.on_start()
        
        # Use GatewayClient from services for proper circuit breaker/tracing
        gw_client = services.gateway_client
        gateway_available = await _check_gateway_available(gateway_url, client=gw_client)
        world_description: dict[str, Any] | None = None
        policy_payload_for_world: dict[str, Any] | None = None
        user_policy_requested = any([preset, preset_overrides, preset_mode, preset_version])

        if gateway_available:
            world_description = await _fetch_world_description(gateway_url, resolved_world, client=gw_client)

        if user_policy_requested and resolved_preset:
            try:
                from .presets import get_preset
                preset_obj = get_preset(resolved_preset)
                policy_payload_for_world = {
                    "preset": preset_obj.name,
                    "policy": preset_obj.to_policy_dict(),
                    "preset_mode": preset_mode,
                    "preset_version": preset_version,
                    "preset_overrides": preset_overrides or {},
                }
                policy_text = _policy_to_human_readable(policy_payload_for_world)
                world_notice.append(
                    f"Using world '{resolved_world}' with preset '{preset_obj.name}' policy: {policy_text}"
                )
            except Exception as exc:
                logger.debug("Failed to build policy from preset %s: %s", resolved_preset, exc)
                policy_payload_for_world = None

        if policy_payload_for_world is None and world_description:
            policy_payload_for_world = world_description.get("policy") if isinstance(world_description, dict) else None
            if isinstance(world_description, dict):
                resolved_preset = world_description.get("policy_preset") or resolved_preset
                human = world_description.get("policy_human") or _policy_to_human_readable(policy_payload_for_world)
                world_notice.append(f"World '{resolved_world}' policy: {human}")

        if policy_payload_for_world is None and resolved_world == DEFAULT_WORLD:
            # Use default preset (sandbox) for zero-config default world submissions
            try:
                from .presets import get_preset
                default_preset_obj = get_preset(resolved_preset or DEFAULT_PRESET)
                policy_payload_for_world = {
                    "preset": default_preset_obj.name,
                    "policy": default_preset_obj.to_policy_dict(),
                }
                policy_text = _policy_to_human_readable(policy_payload_for_world)
                world_notice.append(
                    f"Using default world '__default__' with '{default_preset_obj.name}' preset: {policy_text}. "
                    "Set QMTL_DEFAULT_WORLD to target a custom world or use --preset to override."
                )
                logger.info(
                    "Using default world '__default__' with '%s' preset: %s",
                    default_preset_obj.name,
                    policy_text,
                )
            except Exception as exc:
                logger.debug("Failed to load default preset: %s", exc)

        if policy_payload_for_world is None and resolved_preset:
            try:
                from .presets import get_preset
                preset_obj = get_preset(resolved_preset)
                policy_payload_for_world = {
                    "preset": preset_obj.name,
                    "policy": preset_obj.to_policy_dict(),
                    "preset_mode": preset_mode,
                    "preset_version": preset_version,
                    "preset_overrides": preset_overrides or {},
                }
            except Exception:
                policy_payload_for_world = None

        validation_policy = _policy_from_payload(policy_payload_for_world)

        if gateway_available:
            if policy_payload_for_world is not None:
                await _ensure_world_policy(
                    gateway_url=gateway_url,
                    world_id=resolved_world,
                    payload=policy_payload_for_world,
                    client=gw_client,
                )
            # Submit to gateway for full validation pipeline
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
            strategy_id = bootstrap_result.strategy_id
            
            # Configure activation for non-backtest modes
            if mode != Mode.BACKTEST and not bootstrap_result.offline_mode:
                await Runner._configure_activation(
                    services,
                    strategy_id,
                    gateway_url,
                    resolved_world,
                    bootstrap_result.offline_mode,
                )
        else:
            # Offline mode - local validation only
            logger.info(f"Gateway not available at {gateway_url}, running local validation")
            strategy_id = f"local_{strategy_class_name}_{id(strategy)}"
        
        # Run history warmup and validation
        history_service = services.history_service
        await history_service.warmup_strategy(
            strategy,
            offline_mode=not gateway_available,
            history_start=None,
            history_end=None,
        )
        
        history_service.write_snapshots(strategy)
        strategy.on_finish()
        
        # Extract returns from strategy if not provided
        if returns is not None:
            backtest_returns = list(returns)
        else:
            backtest_returns = _extract_returns_from_strategy(strategy)
        
        # Phase 2: Run automatic validation pipeline
        if auto_validate:
            if not backtest_returns:
                logger.warning(
                    "Strategy %s produced no returns; auto-validation cannot proceed",
                    strategy_class_name,
                )
                return SubmitResult(
                    strategy_id=strategy_id or f"no_returns_{id(strategy)}",
                    status="rejected",
                    world=resolved_world,
                    mode=mode,
                    rejection_reason=(
                        "No returns produced for validation; provide pre-computed "
                        "returns or ensure the strategy populates returns/equity/pnl."
                    ),
                    improvement_hints=[
                        "Ensure your strategy populates returns/equity/pnl during warmup",
                        "Pass pre-computed returns via Runner.submit(..., returns=...)",
                        "Verify history data is available for the selected world/mode",
                    ],
                    metrics=StrategyMetrics(),
                    strategy=strategy,
                )

            validation_pipeline = ValidationPipeline(
                preset=resolved_preset,
                policy=validation_policy,
                world_id=resolved_world,
            )
            validation_result = await validation_pipeline.validate(
                strategy,
                returns=backtest_returns,
            )

            # Optionally ask WorldService (via Gateway) to evaluate/apply policy
            ws_eval = None
            if gateway_available:
                # Convert PerformanceMetrics to StrategyMetrics for WS evaluation
                eval_metrics = StrategyMetrics(
                    sharpe=validation_result.metrics.sharpe,
                    max_drawdown=validation_result.metrics.max_drawdown,
                    win_rate=validation_result.metrics.win_ratio,
                    profit_factor=validation_result.metrics.profit_factor,
                )
                ws_eval = await _evaluate_with_worldservice(
                    gateway_url=gateway_url,
                    world_id=resolved_world,
                    strategy_id=strategy_id or strategy_class_name,
                    metrics=eval_metrics,
                    returns=backtest_returns,
                    preset=resolved_preset,
                    client=gw_client,
                )
                if ws_eval.error:
                    logger.debug("WorldService evaluation fallback error: %s", ws_eval.error)

            # Convert validation result to SubmitResult
            if validation_result.status == ValidationStatus.PASSED:
                # If WS explicitly rejects or reports violations, treat as rejected
                if ws_eval and (ws_eval.active is False or (ws_eval.violations and len(ws_eval.violations) > 0)):
                    rejection_reason = "WorldService evaluation rejected strategy"
                    ws_reject_violations: list[dict[str, object]] = []
                    if ws_eval.violations:
                        for ws_violation in ws_eval.violations:
                            ws_reject_violations.append(
                                {
                                    "metric": ws_violation.get("metric"),
                                    "value": ws_violation.get("value"),
                                    "threshold_type": ws_violation.get("threshold_type") or ws_violation.get("type"),
                                    "threshold_value": ws_violation.get("threshold_value") or ws_violation.get("threshold"),
                                    "message": ws_violation.get("message"),
                                }
                            )
                    return SubmitResult(
                        strategy_id=strategy_id or f"rejected_{id(strategy)}",
                        status="rejected",
                        world=resolved_world,
                        mode=mode,
                        rejection_reason=rejection_reason,
                        improvement_hints=world_notice + validation_result.improvement_hints,
                        threshold_violations=[
                            {
                                "metric": v.metric,
                                "value": v.value,
                                "threshold_type": v.threshold_type,
                                "threshold_value": v.threshold_value,
                                "message": v.message,
                            }
                            for v in validation_result.violations
                        ] + ws_reject_violations,
                        metrics=StrategyMetrics(
                            sharpe=validation_result.metrics.sharpe,
                            max_drawdown=validation_result.metrics.max_drawdown,
                            win_rate=validation_result.metrics.win_ratio,
                            profit_factor=validation_result.metrics.profit_factor,
                        ),
                        strategy=strategy,
                    )

                status = (
                    "active"
                    if (
                        validation_result.activated
                        or (ws_eval and ws_eval.active is True)
                    )
                    else "validated"
                )
                weight: float | None = validation_result.weight
                rank: int | None = validation_result.rank
                contribution: float | None = validation_result.contribution
                # Convert PerformanceMetrics to StrategyMetrics for consistent return type
                metrics_out = StrategyMetrics(
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
                if ws_eval:
                    weight = ws_eval.weight if ws_eval.weight is not None else weight
                    rank = ws_eval.rank if ws_eval.rank is not None else rank
                    contribution = (
                        ws_eval.contribution
                        if ws_eval.contribution is not None
                        else contribution
                    )
                    corr_avg = ws_eval.correlation_avg
                    if corr_avg is not None:
                        metrics_out = StrategyMetrics(
                            sharpe=validation_result.metrics.sharpe,
                            max_drawdown=validation_result.metrics.max_drawdown,
                            correlation_avg=corr_avg,
                            win_rate=validation_result.metrics.win_ratio,
                            profit_factor=validation_result.metrics.profit_factor,
                            car_mdd=validation_result.metrics.car_mdd,
                            rar_mdd=validation_result.metrics.rar_mdd,
                            total_return=validation_result.metrics.total_return,
                            num_trades=validation_result.metrics.num_trades,
                        )
                return SubmitResult(
                    strategy_id=strategy_id or f"unknown_{id(strategy)}",
                    status=status,
                    world=resolved_world,
                    mode=mode,
                    contribution=contribution,
                    weight=weight,
                    rank=rank,
                    metrics=metrics_out,
                    strategy=strategy,
                    improvement_hints=world_notice + validation_result.improvement_hints,
                )
            elif validation_result.status == ValidationStatus.FAILED:
                # When Gateway is available, defer to WorldService evaluation.
                # Local validation may lack world state (existing strategies, correlation data),
                # so WS evaluation is the source of truth for world-aware decisions.
                if gateway_available and ws_eval and ws_eval.active is True:
                    # WS accepts the strategy despite local rejection - trust WS
                    logger.info(
                        "Local validation failed but WorldService accepted strategy %s; "
                        "deferring to WS decision (local lacks world state)",
                        strategy_id or strategy_class_name,
                    )
                    # Log local violations as warnings for visibility
                    for v in validation_result.violations:
                        logger.warning(
                            "Local validation warning (overridden by WS): %s=%s (threshold %s %s)",
                            v.metric, v.value, v.threshold_type, v.threshold_value,
                        )
                    weight = ws_eval.weight
                    rank = ws_eval.rank
                    contribution = ws_eval.contribution
                    corr_avg = ws_eval.correlation_avg
                    metrics_out = StrategyMetrics(
                        sharpe=validation_result.metrics.sharpe,
                        max_drawdown=validation_result.metrics.max_drawdown,
                        win_rate=validation_result.metrics.win_ratio,
                        profit_factor=validation_result.metrics.profit_factor,
                        correlation_avg=corr_avg,
                        car_mdd=validation_result.metrics.car_mdd,
                        rar_mdd=validation_result.metrics.rar_mdd,
                        total_return=validation_result.metrics.total_return,
                        num_trades=validation_result.metrics.num_trades,
                    )
                    return SubmitResult(
                        strategy_id=strategy_id or f"ws_accepted_{id(strategy)}",
                        status="active",
                        world=resolved_world,
                        mode=mode,
                        contribution=contribution,
                        weight=weight,
                        rank=rank,
                        metrics=metrics_out,
                        strategy=strategy,
                        improvement_hints=world_notice + [
                            "Note: Local validation failed but WorldService accepted with world-aware metrics"
                        ] + validation_result.improvement_hints,
                    )

                # Gateway available but WS eval failed/unavailable - defer decision, don't reject locally
                if gateway_available and (ws_eval is None or ws_eval.error):
                    ws_error_msg = ws_eval.error if ws_eval else "WS evaluation unavailable"
                    logger.warning(
                        "Local validation failed for %s but WS evaluation also failed (%s); "
                        "deferring to Gateway with 'pending' status (local validation lacks world state)",
                        strategy_id or strategy_class_name,
                        ws_error_msg,
                    )
                    # Log local violations as warnings
                    for v in validation_result.violations:
                        logger.warning(
                            "Local validation warning (WS unavailable): %s=%s (threshold %s %s)",
                            v.metric, v.value, v.threshold_type, v.threshold_value,
                        )
                    return SubmitResult(
                        strategy_id=strategy_id or f"pending_{id(strategy)}",
                        status="pending",
                        world=resolved_world,
                        mode=mode,
                        metrics=StrategyMetrics(
                            sharpe=validation_result.metrics.sharpe,
                            max_drawdown=validation_result.metrics.max_drawdown,
                            win_rate=validation_result.metrics.win_ratio,
                            profit_factor=validation_result.metrics.profit_factor,
                        ),
                        strategy=strategy,
                        improvement_hints=world_notice + [
                            f"Local validation failed but WS evaluation unavailable ({ws_error_msg}); "
                            "strategy submitted as pending for server-side evaluation"
                        ] + validation_result.improvement_hints,
                        threshold_violations=[
                            {
                                "metric": v.metric,
                                "value": v.value,
                                "threshold_type": v.threshold_type,
                                "threshold_value": v.threshold_value,
                                "message": v.message,
                            }
                            for v in validation_result.violations
                        ],
                    )

                # Gateway not available OR WS explicitly rejected - apply local rejection
                rejection_reason = "Strategy did not meet policy thresholds"
                if ws_eval and ws_eval.active is False:
                    rejection_reason = "WorldService evaluation rejected strategy"
                if ws_eval and ws_eval.error:
                    rejection_reason += f" (WS error: {ws_eval.error})"
                ws_extra_violations: list[dict[str, object]] = []
                if ws_eval and ws_eval.violations:
                    validation_result.improvement_hints.extend(
                        [
                            str(ws_violation.get("message", ""))
                            for ws_violation in ws_eval.violations
                            if ws_violation.get("message")
                        ]
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
                return SubmitResult(
                    strategy_id=strategy_id or f"rejected_{id(strategy)}",
                    status="rejected",
                    world=resolved_world,
                    mode=mode,
                    rejection_reason=rejection_reason,
                    improvement_hints=world_notice + validation_result.improvement_hints,
                    threshold_violations=[
                        {
                            "metric": v.metric,
                            "value": v.value,
                            "threshold_type": v.threshold_type,
                            "threshold_value": v.threshold_value,
                            "message": v.message,
                        }
                        for v in validation_result.violations
                    ] + ws_extra_violations,
                    metrics=StrategyMetrics(
                        sharpe=validation_result.metrics.sharpe,
                        max_drawdown=validation_result.metrics.max_drawdown,
                        win_rate=validation_result.metrics.win_ratio,
                        profit_factor=validation_result.metrics.profit_factor,
                    ),
                    strategy=strategy,
                )
            else:
                # ERROR status
                return SubmitResult(
                    strategy_id=strategy_id or f"error_{id(strategy)}",
                    status="rejected",
                    world=resolved_world,
                    mode=mode,
                    rejection_reason=validation_result.error_message or "Validation error",
                    improvement_hints=world_notice + validation_result.improvement_hints,
                    strategy=strategy,
                )
        
        # No auto-validation or no returns: return basic result
        return SubmitResult(
            strategy_id=strategy_id or f"unknown_{id(strategy)}",
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
        
    except Exception as e:
        try:
            strategy.on_error(e)
        except Exception:
            logger.exception("strategy.on_error raised during failure handling")

        return SubmitResult(
            strategy_id=strategy_id or f"failed_{id(strategy)}",
            status="rejected",
            world=resolved_world,
            mode=mode,
            rejection_reason=str(e),
            improvement_hints=world_notice + _get_improvement_hints(e),
            strategy=strategy if 'strategy' in locals() else None,
        )


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


def submit(
    strategy_cls: type["Strategy"],
    *,
    world: str | None = None,
    mode: Mode | str = Mode.BACKTEST,
    preset: str | None = None,
    preset_mode: str | None = None,
    preset_version: str | None = None,
    preset_overrides: dict[str, float] | None = None,
    returns: Sequence[float] | None = None,
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
    returns : Sequence[float], optional
        Pre-computed backtest returns.
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
        world=world,
        mode=mode,
        preset=preset,
        preset_mode=preset_mode,
        preset_version=preset_version,
        preset_overrides=preset_overrides,
        returns=returns,
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
            # Use describe_world to get full policy info
            return await client.describe_world(gateway_url=gateway_url, world_id=world_id)
        # Fallback to direct httpx if no client provided
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.get(f"{gateway_url.rstrip('/')}/worlds/{world_id}/describe")
            if resp.status_code == 404:
                return None
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


def _parse_ws_eval_response(data: dict[str, Any], strategy_id: str) -> WsEvalResult:
    """Parse WorldService evaluation response into WsEvalResult."""
    active_list = data.get("active", [])
    weights = data.get("weights", {}) or {}
    contributions = data.get("contributions", {}) or data.get("contribution", {}) or {}
    ranks = data.get("ranks", {}) or {}
    violations = data.get("violations") or data.get("threshold_violations")
    correlation_avg = data.get("correlation_avg") or data.get("correlation")

    is_active = None
    if isinstance(active_list, list):
        is_active = strategy_id in active_list

    weight = None
    contribution = None
    rank = None
    if isinstance(weights, dict):
        weight = weights.get(strategy_id)
    if isinstance(contributions, dict):
        contribution = contributions.get(strategy_id)
    if isinstance(ranks, dict):
        rank = ranks.get(strategy_id)

    return WsEvalResult(
        active=is_active,
        weight=weight,
        contribution=contribution,
        rank=rank,
        violations=violations if isinstance(violations, list) else None,
        correlation_avg=float(correlation_avg) if isinstance(correlation_avg, (int, float)) else None,
    )
