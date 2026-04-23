"""Helpers for mapping validation + WS evaluation into ``SubmitResult``."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .strategy import Strategy


def build_submit_result_from_validation(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
    gateway_available: bool,
) -> Any:
    from .validation_pipeline import ValidationStatus

    if validation_result.status == ValidationStatus.PASSED:
        return _build_passed_result(
            strategy=strategy,
            strategy_id=strategy_id,
            resolved_world=resolved_world,
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
            world_notice=world_notice,
            validation_result=validation_result,
            ws_eval=ws_eval,
            gateway_available=gateway_available,
        )
    return _build_error_result(
        strategy=strategy,
        strategy_id=strategy_id,
        resolved_world=resolved_world,
        world_notice=world_notice,
        validation_result=validation_result,
        ws_eval=ws_eval,
    )


def _build_passed_result(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
) -> Any:
    precheck = _precheck_from_validation(validation_result)
    rejection = _maybe_ws_rejection_with_precheck(
        strategy=strategy,
        strategy_id=strategy_id,
        resolved_world=resolved_world,
        world_notice=world_notice,
        validation_result=validation_result,
        ws_eval=ws_eval,
        precheck=precheck,
    )
    if rejection is not None:
        return rejection

    status = _resolved_status(validation_result, ws_eval)
    weight, rank, contribution = _resolve_ws_eval_fields(validation_result, ws_eval)
    metrics_out = _metrics_from_validation_and_ws(validation_result, ws_eval)
    eval_run_id, eval_run_url = _evaluation_run_fields(ws_eval)

    return _submit_result(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy),
        status=status,
        world=resolved_world,
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
        evaluation_run_id=eval_run_id,
        evaluation_run_url=eval_run_url,
    )


def _build_failed_result(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
    gateway_available: bool,
) -> Any:
    if gateway_available and ws_eval and ws_eval.active is True:
        return _ws_accepts_after_fail(
            strategy=strategy,
            strategy_class_name=strategy_class_name,
            strategy_id=strategy_id,
            resolved_world=resolved_world,
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
            world_notice=world_notice,
            validation_result=validation_result,
            ws_eval=ws_eval,
        )

    return _reject_after_failed_validation(
        strategy=strategy,
        strategy_id=strategy_id,
        resolved_world=resolved_world,
        world_notice=world_notice,
        validation_result=validation_result,
        ws_eval=ws_eval,
    )


def _build_error_result(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
) -> Any:
    eval_run_id, eval_run_url = _evaluation_run_fields(ws_eval)
    return _submit_result(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="error"),
        status="rejected",
        world=resolved_world,
        rejection_reason=validation_result.error_message or "Validation error",
        improvement_hints=world_notice + validation_result.improvement_hints,
        strategy=strategy,
        precheck=_precheck_from_validation(validation_result),
        evaluation_run_id=eval_run_id,
        evaluation_run_url=eval_run_url,
    )


def _maybe_ws_rejection_with_precheck(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
    precheck: Any | None,
) -> Any | None:
    rejection = _ws_rejection_result(
        strategy=strategy,
        strategy_id=strategy_id,
        resolved_world=resolved_world,
        world_notice=world_notice,
        validation_result=validation_result,
        ws_eval=ws_eval,
    )
    if rejection is None:
        return None
    rejection.precheck = precheck
    return rejection


def _ws_rejection_result(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
) -> Any | None:
    if ws_eval is None:
        return None
    has_rejection = ws_eval.active is False or bool(ws_eval.violations)
    if not has_rejection:
        return None
    ws_reject_violations = _final_threshold_violations(validation_result, ws_eval)
    eval_run_id, eval_run_url = _evaluation_run_fields(ws_eval)
    return _submit_result(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="rejected"),
        status="rejected",
        world=resolved_world,
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
        evaluation_run_id=eval_run_id,
        evaluation_run_url=eval_run_url,
    )


def _resolved_status(validation_result: Any, ws_eval: Any | None) -> str:
    from .validation_pipeline import ValidationStatus

    if ws_eval is not None:
        if ws_eval.active is True:
            return "active"
        if ws_eval.active is False:
            return "rejected"
        if ws_eval.error:
            return "pending"
        return "pending"

    if getattr(validation_result, "status", None) == ValidationStatus.FAILED:
        return "rejected"
    return "pending"


def _resolve_ws_eval_fields(
    validation_result: Any,
    ws_eval: Any | None,
) -> tuple[float | None, int | None, float | None]:
    if ws_eval is None:
        return (
            getattr(validation_result, "weight", None),
            getattr(validation_result, "rank", None),
            getattr(validation_result, "contribution", None),
        )
    return ws_eval.weight, ws_eval.rank, ws_eval.contribution


def _metrics_from_validation_and_ws(
    validation_result: Any,
    ws_eval: Any | None,
) -> Any:
    metrics_out = _base_metrics_from_validation(validation_result)
    if ws_eval and ws_eval.correlation_avg is not None:
        return _clone_metrics_with_corr(metrics_out, ws_eval.correlation_avg)
    return metrics_out


def _evaluation_run_fields(ws_eval: Any | None) -> tuple[str | None, str | None]:
    if ws_eval is None:
        return None, None
    return ws_eval.evaluation_run_id, ws_eval.evaluation_run_url


def _ws_accepts_after_fail(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any,
) -> Any:
    _logger().info(
        "Local validation failed but WorldService accepted strategy %s; deferring to WS decision",
        strategy_id or strategy_class_name,
    )
    for violation in getattr(validation_result, "violations", []):
        _logger().warning(
            "Local validation warning (overridden by WS): %s=%s (threshold %s %s)",
            violation.metric,
            violation.value,
            violation.threshold_type,
            violation.threshold_value,
        )
    metrics_out = _clone_metrics_with_corr(
        _base_metrics_from_validation(validation_result),
        ws_eval.correlation_avg,
    )
    eval_run_id, eval_run_url = _evaluation_run_fields(ws_eval)
    return _submit_result(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="ws_accepted"),
        status="active",
        world=resolved_world,
        contribution=ws_eval.contribution,
        weight=ws_eval.weight,
        rank=ws_eval.rank,
        metrics=metrics_out,
        strategy=strategy,
        improvement_hints=world_notice
        + ["Note: Local validation failed but WorldService accepted with world-aware metrics"]
        + validation_result.improvement_hints,
        precheck=_precheck_from_validation(validation_result),
        decision=ws_eval.decision,
        activation=ws_eval.activation,
        allocation=ws_eval.allocation,
        allocation_notice=ws_eval.allocation_notice,
        allocation_stale=ws_eval.allocation_stale,
        evaluation_run_id=eval_run_id,
        evaluation_run_url=eval_run_url,
    )


def _pending_after_failed_validation(
    *,
    strategy: "Strategy",
    strategy_class_name: str,
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
) -> Any:
    ws_error_msg = ws_eval.error if ws_eval else "WS evaluation unavailable"
    _logger().warning(
        "Local validation failed for %s but WS evaluation also failed (%s); deferring with pending status",
        strategy_id or strategy_class_name,
        ws_error_msg,
    )
    for violation in getattr(validation_result, "violations", []):
        _logger().warning(
            "Local validation warning (WS unavailable): %s=%s (threshold %s %s)",
            violation.metric,
            violation.value,
            violation.threshold_type,
            violation.threshold_value,
        )
    eval_run_id, eval_run_url = _evaluation_run_fields(ws_eval)
    return _submit_result(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="pending"),
        status="pending",
        world=resolved_world,
        metrics=_base_metrics_from_validation(validation_result),
        strategy=strategy,
        improvement_hints=world_notice
        + [
            f"Local validation failed but WS evaluation unavailable ({ws_error_msg}); strategy submitted as pending for server-side evaluation"
        ]
        + validation_result.improvement_hints,
        threshold_violations=_final_threshold_violations(validation_result, ws_eval),
        precheck=_precheck_from_validation(validation_result),
        decision=ws_eval.decision if ws_eval else None,
        activation=ws_eval.activation if ws_eval else None,
        allocation=ws_eval.allocation if ws_eval else None,
        allocation_notice=ws_eval.allocation_notice if ws_eval else None,
        allocation_stale=ws_eval.allocation_stale if ws_eval else False,
        evaluation_run_id=eval_run_id,
        evaluation_run_url=eval_run_url,
    )


def _reject_after_failed_validation(
    *,
    strategy: "Strategy",
    strategy_id: str | None,
    resolved_world: str,
    world_notice: list[str],
    validation_result: Any,
    ws_eval: Any | None,
) -> Any:
    rejection_reason, ws_extra_violations = _rejection_details(ws_eval, validation_result)
    final_thresholds = (
        ws_extra_violations
        if ws_extra_violations
        else _final_threshold_violations(validation_result, ws_eval)
    )
    eval_run_id, eval_run_url = _evaluation_run_fields(ws_eval)
    return _submit_result(
        strategy_id=_strategy_id_or_fallback(strategy_id, strategy, prefix="rejected"),
        status="rejected",
        world=resolved_world,
        rejection_reason=rejection_reason,
        improvement_hints=world_notice + validation_result.improvement_hints,
        threshold_violations=final_thresholds,
        metrics=_strategy_metrics(
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
        evaluation_run_id=eval_run_id,
        evaluation_run_url=eval_run_url,
    )


def _rejection_details(
    ws_eval: Any | None,
    validation_result: Any,
) -> tuple[str, list[dict[str, object]]]:
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
            [
                str(item.get("message", ""))
                for item in ws_eval.violations
                if item.get("message")
            ]
        )
        for item in ws_eval.violations:
            ws_extra_violations.append(
                {
                    "metric": item.get("metric"),
                    "value": item.get("value"),
                    "threshold_type": item.get("threshold_type") or item.get("type"),
                    "threshold_value": item.get("threshold_value") or item.get("threshold"),
                    "message": item.get("message"),
                }
            )
    return rejection_reason, ws_extra_violations


def _strategy_id_or_fallback(
    strategy_id: str | None,
    strategy: "Strategy",
    *,
    prefix: str = "unknown",
) -> str:
    return strategy_id or f"{prefix}_{id(strategy)}"


def _base_metrics_from_validation(validation_result: Any) -> Any:
    metrics = validation_result.metrics
    return _strategy_metrics(
        sharpe=metrics.sharpe,
        max_drawdown=metrics.max_drawdown,
        win_rate=metrics.win_ratio,
        profit_factor=metrics.profit_factor,
        car_mdd=metrics.car_mdd,
        rar_mdd=metrics.rar_mdd,
        total_return=metrics.total_return,
        num_trades=metrics.num_trades,
        correlation_avg=getattr(validation_result, "correlation_avg", None),
    )


def _validation_violations(validation_result: Any) -> list[dict[str, object]]:
    return [
        {
            "metric": violation.metric,
            "value": violation.value,
            "threshold_type": violation.threshold_type,
            "threshold_value": violation.threshold_value,
            "message": violation.message,
        }
        for violation in getattr(validation_result, "violations", [])
    ]


def _final_threshold_violations(
    validation_result: Any,
    ws_eval: Any | None,
) -> list[dict[str, object]]:
    violations = getattr(ws_eval, "violations", None)
    if isinstance(violations, list):
        normalized: list[dict[str, object]] = []
        for item in violations:
            if isinstance(item, dict):
                normalized.append(dict(item))
        if normalized:
            return normalized
    return _validation_violations(validation_result)


def _precheck_from_validation(validation_result: Any) -> Any:
    try:
        status_value = validation_result.status.value
    except Exception:
        status_value = str(getattr(validation_result, "status", "pending"))

    return _precheck_result(
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


def _clone_metrics_with_corr(
    metrics: Any,
    correlation_avg: float | None,
) -> Any:
    if correlation_avg is None:
        return metrics
    return _strategy_metrics(
        sharpe=metrics.sharpe,
        max_drawdown=metrics.max_drawdown,
        correlation_avg=correlation_avg,
        win_rate=metrics.win_rate,
        profit_factor=metrics.profit_factor,
        car_mdd=metrics.car_mdd,
        rar_mdd=metrics.rar_mdd,
        total_return=metrics.total_return,
        num_trades=metrics.num_trades,
        adv_utilization_p95=metrics.adv_utilization_p95,
        participation_rate_p95=metrics.participation_rate_p95,
    )


def _submit_module() -> Any:
    return import_module("qmtl.runtime.sdk.submit")


def _submit_result(**kwargs: Any) -> Any:
    return _submit_module().SubmitResult(**kwargs)


def _strategy_metrics(**kwargs: Any) -> Any:
    return _submit_module().StrategyMetrics(**kwargs)


def _precheck_result(**kwargs: Any) -> Any:
    return _submit_module().PrecheckResult(**kwargs)


def _logger() -> Any:
    return _submit_module().logger
