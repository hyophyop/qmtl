"""Invariant and validation-health helpers for WorldService."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .metrics import parse_timestamp

V1_CORE_METRIC_PATHS: tuple[tuple[str, str], ...] = (
    ("returns", "sharpe"),
    ("returns", "max_drawdown"),
    ("returns", "gain_to_pain_ratio"),
    ("returns", "time_under_water_ratio"),
    ("sample", "effective_history_years"),
    ("sample", "n_trades_total"),
    ("sample", "n_trades_per_year"),
    ("risk", "adv_utilization_p95"),
    ("risk", "participation_rate_p95"),
    ("robustness", "deflated_sharpe_ratio"),
    ("robustness", "sharpe_first_half"),
    ("robustness", "sharpe_second_half"),
)

# v1 core rule set: DataCurrency, Sample, Performance, RiskConstraint, Robustness
DEFAULT_RULE_COUNT = 5


@dataclass
class InvariantReport:
    """Container for validation invariant results."""

    live_status_failures: list[dict[str, Any]]
    live_policy_version_mismatches: list[dict[str, Any]]
    fail_closed_violations: list[dict[str, Any]]
    approved_overrides: list[dict[str, Any]]
    validation_health_gaps: list[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return not (
            self.live_status_failures
            or self.live_policy_version_mismatches
            or self.fail_closed_violations
            or self.approved_overrides
            or self.validation_health_gaps
        )


def _metric_coverage_ratio(metrics: Mapping[str, Any] | None) -> float:
    if not metrics:
        return 0.0
    present = 0
    for section, name in V1_CORE_METRIC_PATHS:
        slot = metrics.get(section)
        if isinstance(slot, Mapping) and slot.get(name) is not None:
            present += 1
    total = len(V1_CORE_METRIC_PATHS)
    return present / total if total else 0.0


def _rules_executed_ratio(
    rule_results: Mapping[str, Any] | None,
    expected_rules: int = DEFAULT_RULE_COUNT,
) -> float:
    if expected_rules <= 0:
        return 0.0
    executed = len(rule_results or {})
    return min(1.0, executed / expected_rules)


def _validation_error_count(rule_results: Mapping[str, Any] | None) -> int:
    """Count rule evaluation errors (reason_code == 'rule_error')."""

    if not rule_results:
        return 0
    count = 0
    for result in rule_results.values():
        reason_code: Any = None
        if isinstance(result, Mapping):
            reason_code = result.get("reason_code")
        else:
            reason_code = getattr(result, "reason_code", None)
        if str(reason_code or "").lower() == "rule_error":
            count += 1
    return count


def compute_validation_health(
    metrics: Mapping[str, Any] | None,
    rule_results: Mapping[str, Any] | None,
    *,
    expected_rules: int = DEFAULT_RULE_COUNT,
) -> dict[str, float | int]:
    """Derive validation health signals from metrics and executed rules."""

    return {
        "metric_coverage_ratio": _metric_coverage_ratio(metrics),
        "rules_executed_ratio": _rules_executed_ratio(rule_results, expected_rules),
        "validation_error_count": _validation_error_count(rule_results),
    }


def ensure_validation_health(
    metrics: Mapping[str, Any] | None,
    rule_results: Mapping[str, Any] | None,
    *,
    expected_rules: int = DEFAULT_RULE_COUNT,
) -> dict[str, Any]:
    """Attach validation_health metrics to an EvaluationMetrics mapping.

    Returns a deep-copied metrics mapping with diagnostics.validation_health filled.
    """

    base = deepcopy(metrics) if metrics else {}
    diagnostics = base.setdefault("diagnostics", {})
    health = dict(diagnostics.get("validation_health") or {})
    derived = compute_validation_health(base, rule_results, expected_rules=expected_rules)
    health.update(derived)
    diagnostics["validation_health"] = health
    base["diagnostics"] = diagnostics
    return base


def _world_is_high_tier_and_critical(world: Mapping[str, Any]) -> bool:
    profile = world.get("risk_profile") or {}
    tier = str(profile.get("tier", "")).lower()
    critical = bool(profile.get("client_critical") or world.get("client_critical"))
    return tier == "high" and critical


def _validation_policy(world: Mapping[str, Any]) -> Mapping[str, Any]:
    validation = world.get("validation")
    return validation if isinstance(validation, Mapping) else {}


def _timestamp_key(run: Mapping[str, Any], index: int) -> tuple[datetime, int]:
    ts = parse_timestamp(run.get("created_at") or run.get("updated_at"))
    return (ts or datetime.min, index)


def _latest_live_runs(runs: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    per_strategy: dict[Any, tuple[tuple[datetime, int], Mapping[str, Any]]] = {}
    for idx, run in enumerate(runs):
        strategy_id = run.get("strategy_id")
        key = _timestamp_key(run, idx)
        if strategy_id not in per_strategy or key > per_strategy[strategy_id][0]:
            per_strategy[strategy_id] = (key, run)
    return [entry[1] for entry in per_strategy.values()]


def _recorded_health(metrics: Mapping[str, Any] | None) -> dict[str, float | int | None]:
    diagnostics = metrics.get("diagnostics") if isinstance(metrics, Mapping) else None
    health = diagnostics.get("validation_health") if isinstance(diagnostics, Mapping) else None
    if not isinstance(health, Mapping):
        return {
            "metric_coverage_ratio": None,
            "rules_executed_ratio": None,
            "validation_error_count": None,
        }
    return {
        "metric_coverage_ratio": health.get("metric_coverage_ratio"),
        "rules_executed_ratio": health.get("rules_executed_ratio"),
        "validation_error_count": health.get("validation_error_count"),
    }


def _close(a: float | None, b: float | None, *, tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def _parse_policy_version(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _isoformat_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _override_review_window_days(world: Mapping[str, Any], run: Mapping[str, Any]) -> int:
    """Return override re-review window in days (Invariant 3)."""

    stage = str(run.get("stage") or "").lower()
    if stage == "live":
        return 30
    if _world_is_high_tier_and_critical(world):
        return 30
    return 90


def check_validation_invariants(
    world: Mapping[str, Any],
    evaluation_runs: Iterable[Mapping[str, Any]],
) -> InvariantReport:
    """Evaluate validation invariants for a world and its evaluation runs."""

    runs = list(evaluation_runs)
    world_id = world.get("id") or world.get("world_id")
    required_policy_version = _parse_policy_version(world.get("default_policy_version"))

    live_runs = [
        run for run in runs if str(run.get("stage", "")).lower() == "live"
    ]
    latest_live = _latest_live_runs(live_runs)

    live_failures: list[dict[str, Any]] = []
    live_policy_version_mismatches: list[dict[str, Any]] = []
    for run in latest_live:
        summary = run.get("summary") or {}
        status = str(summary.get("status", "")).lower()
        if status != "pass":
            live_failures.append(
                {
                    "world_id": world_id or run.get("world_id"),
                    "strategy_id": run.get("strategy_id"),
                    "run_id": run.get("run_id"),
                    "status": summary.get("status"),
                }
            )

        if required_policy_version is not None:
            validation = run.get("validation") if isinstance(run, Mapping) else {}
            run_version_raw = (
                validation.get("policy_version") if isinstance(validation, Mapping) else None
            )
            run_version = _parse_policy_version(run_version_raw)
            if run_version is None or run_version < required_policy_version:
                live_policy_version_mismatches.append(
                    {
                        "world_id": world_id or run.get("world_id"),
                        "strategy_id": run.get("strategy_id"),
                        "run_id": run.get("run_id"),
                        "policy_version": run_version_raw,
                        "required_policy_version": required_policy_version,
                    }
                )

    fail_closed_violations: list[dict[str, Any]] = []
    if _world_is_high_tier_and_critical(world):
        validation = _validation_policy(world)
        on_error = str(validation.get("on_error", "")).lower() or None
        on_missing = str(validation.get("on_missing_metric", "")).lower() or None
        if on_error != "fail" or on_missing != "fail":
            fail_closed_violations.append(
                {
                    "world_id": world_id,
                    "on_error": on_error or "<unset>",
                    "on_missing_metric": on_missing or "<unset>",
                }
            )

    approved_overrides: list[dict[str, Any]] = []
    validation_health_gaps: list[dict[str, Any]] = []
    for run in runs:
        summary = run.get("summary") or {}
        if str(summary.get("override_status", "")).lower() == "approved":
            override_reason = summary.get("override_reason")
            override_actor = summary.get("override_actor")
            override_timestamp = summary.get("override_timestamp")
            window_days = _override_review_window_days(world, run)
            override_ts = parse_timestamp(str(override_timestamp)) if override_timestamp else None
            review_due_at = None
            review_overdue = None
            if override_ts is not None:
                due_dt = override_ts + timedelta(days=window_days)
                review_due_at = _isoformat_utc(due_dt)
                review_overdue = datetime.now(timezone.utc) > due_dt
            missing_fields = [
                key
                for key, value in (
                    ("override_reason", override_reason),
                    ("override_actor", override_actor),
                    ("override_timestamp", override_timestamp),
                )
                if not value
            ]
            approved_overrides.append(
                {
                    "world_id": world_id or run.get("world_id"),
                    "strategy_id": run.get("strategy_id"),
                    "run_id": run.get("run_id"),
                    "stage": run.get("stage"),
                    "override_reason": override_reason,
                    "override_actor": override_actor,
                    "override_timestamp": override_timestamp,
                    "review_window_days": window_days,
                    "review_due_at": review_due_at,
                    "review_overdue": review_overdue,
                    "missing_fields": missing_fields,
                }
            )

        validation = run.get("validation") if isinstance(run, Mapping) else {}
        rule_results = validation.get("results") if isinstance(validation, Mapping) else {}
        expected = compute_validation_health(run.get("metrics"), rule_results)
        recorded = _recorded_health(run.get("metrics"))

        if not _close(recorded["metric_coverage_ratio"], expected["metric_coverage_ratio"]):
            validation_health_gaps.append(
                {
                    "world_id": world_id or run.get("world_id"),
                    "strategy_id": run.get("strategy_id"),
                    "run_id": run.get("run_id"),
                    "metric": "metric_coverage_ratio",
                    "expected": expected["metric_coverage_ratio"],
                    "recorded": recorded["metric_coverage_ratio"],
                }
            )
        if not _close(recorded["rules_executed_ratio"], expected["rules_executed_ratio"]):
            validation_health_gaps.append(
                {
                    "world_id": world_id or run.get("world_id"),
                    "strategy_id": run.get("strategy_id"),
                    "run_id": run.get("run_id"),
                    "metric": "rules_executed_ratio",
                    "expected": expected["rules_executed_ratio"],
                    "recorded": recorded["rules_executed_ratio"],
                }
            )
        if recorded["validation_error_count"] != expected["validation_error_count"]:
            validation_health_gaps.append(
                {
                    "world_id": world_id or run.get("world_id"),
                    "strategy_id": run.get("strategy_id"),
                    "run_id": run.get("run_id"),
                    "metric": "validation_error_count",
                    "expected": expected["validation_error_count"],
                    "recorded": recorded["validation_error_count"],
                }
            )

    return InvariantReport(
        live_status_failures=live_failures,
        live_policy_version_mismatches=live_policy_version_mismatches,
        fail_closed_violations=fail_closed_violations,
        approved_overrides=approved_overrides,
        validation_health_gaps=validation_health_gaps,
    )


__all__ = [
    "InvariantReport",
    "DEFAULT_RULE_COUNT",
    "V1_CORE_METRIC_PATHS",
    "check_validation_invariants",
    "compute_validation_health",
    "ensure_validation_health",
]
