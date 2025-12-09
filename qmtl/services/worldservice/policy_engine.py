from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Protocol, Sequence, Tuple

import yaml
from pydantic import BaseModel, Field


def _flatten_metrics(values: Mapping[str, Any] | None) -> Dict[str, float]:
    """Flatten nested metric payloads into a simple name -> float mapping."""
    if not values:
        return {}

    flat: Dict[str, float] = {}
    for key, value in values.items():
        if isinstance(value, Mapping):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, (int, float)) and not isinstance(sub_value, bool):
                    flat[sub_key] = float(sub_value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            flat[key] = float(value)
    return flat


def _normalize_metrics(metrics: Mapping[str, Mapping[str, Any]] | None) -> Dict[str, Dict[str, float]]:
    """Normalize raw metrics to a per-strategy flat mapping."""
    normalized: Dict[str, Dict[str, float]] = {}
    if not metrics:
        return normalized
    for strategy_id, values in metrics.items():
        normalized[strategy_id] = _flatten_metrics(values)
    return normalized


class RuleResult(BaseModel):
    status: str
    severity: str = "blocking"
    owner: str = "quant"
    reason_code: str
    reason: str
    tags: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class RuleContext:
    strategy_id: str
    previous_active: Iterable[str] | None = None
    correlations: Dict[Tuple[str, str], float] | None = None


class ValidationRule(Protocol):
    name: str

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        ...


@dataclass
class PolicyEvaluationResult(Iterable[str]):
    selected_ids: List[str]
    rule_results: Dict[str, Dict[str, RuleResult]] = field(default_factory=dict)
    profile: str | None = None

    def __iter__(self) -> Iterator[str]:
        return iter(self.selected_ids)

    def __len__(self) -> int:
        return len(self.selected_ids)

    def __contains__(self, item: object) -> bool:
        return item in self.selected_ids

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PolicyEvaluationResult):
            return (
                self.selected_ids == other.selected_ids
                and self.rule_results == other.rule_results
                and self.profile == other.profile
            )
        if isinstance(other, list):
            return self.selected_ids == other
        return False

    @property
    def selected(self) -> List[str]:
        return self.selected_ids

    @property
    def selected_ids_compat(self) -> List[str]:
        """Alias for older callers expecting a selected_ids attribute."""
        return self.selected_ids

    def for_strategy(self, strategy_id: str) -> Dict[str, RuleResult]:
        return self.rule_results.get(strategy_id, {})


class ThresholdRule(BaseModel):
    metric: str
    min: float | None = None
    max: float | None = None


class TopKRule(BaseModel):
    metric: str
    k: int = Field(gt=0)


class CorrelationRule(BaseModel):
    max: float = Field(ge=-1.0, le=1.0)


class HysteresisRule(BaseModel):
    metric: str
    enter: float
    exit: float


class SampleProfile(BaseModel):
    min_effective_years: float | None = None
    min_trades_total: int | None = None

    def to_thresholds(self) -> Dict[str, ThresholdRule]:
        thresholds: Dict[str, ThresholdRule] = {}
        if self.min_effective_years is not None:
            thresholds["effective_history_years"] = ThresholdRule(
                metric="effective_history_years",
                min=float(self.min_effective_years),
            )
        if self.min_trades_total is not None:
            thresholds["n_trades_total"] = ThresholdRule(
                metric="n_trades_total",
                min=float(self.min_trades_total),
            )
        return thresholds


class PerformanceProfile(BaseModel):
    sharpe_min: float | None = None
    max_dd_max: float | None = None
    gain_to_pain_min: float | None = None

    def to_thresholds(self) -> Dict[str, ThresholdRule]:
        thresholds: Dict[str, ThresholdRule] = {}
        if self.sharpe_min is not None:
            thresholds["sharpe"] = ThresholdRule(metric="sharpe", min=float(self.sharpe_min))
        if self.max_dd_max is not None:
            thresholds["max_drawdown"] = ThresholdRule(metric="max_drawdown", max=float(self.max_dd_max))
        if self.gain_to_pain_min is not None:
            thresholds["gain_to_pain_ratio"] = ThresholdRule(
                metric="gain_to_pain_ratio",
                min=float(self.gain_to_pain_min),
            )
        return thresholds


class RobustnessProfile(BaseModel):
    dsr_min: float | None = None
    severity: str | None = None  # reserved for v1.5+ metadata passthrough
    owner: str | None = None     # reserved for v1.5+ metadata passthrough

    def to_thresholds(self) -> Dict[str, ThresholdRule]:
        thresholds: Dict[str, ThresholdRule] = {}
        if self.dsr_min is not None:
            thresholds["deflated_sharpe_ratio"] = ThresholdRule(
                metric="deflated_sharpe_ratio",
                min=float(self.dsr_min),
            )
        return thresholds


class RiskProfile(BaseModel):
    adv_utilization_p95_max: float | None = None
    participation_rate_p95_max: float | None = None

    def to_thresholds(self) -> Dict[str, ThresholdRule]:
        thresholds: Dict[str, ThresholdRule] = {}
        if self.adv_utilization_p95_max is not None:
            thresholds["adv_utilization_p95"] = ThresholdRule(
                metric="adv_utilization_p95",
                max=float(self.adv_utilization_p95_max),
            )
        if self.participation_rate_p95_max is not None:
            thresholds["participation_rate_p95"] = ThresholdRule(
                metric="participation_rate_p95",
                max=float(self.participation_rate_p95_max),
            )
        return thresholds


class ValidationProfile(BaseModel):
    sample: SampleProfile | None = None
    performance: PerformanceProfile | None = None
    robustness: RobustnessProfile | None = None
    risk: RiskProfile | None = None

    def to_thresholds(self) -> Dict[str, ThresholdRule]:
        thresholds: Dict[str, ThresholdRule] = {}
        for section in (self.sample, self.performance, self.robustness, self.risk):
            if section:
                thresholds.update(section.to_thresholds())
        return thresholds


class SelectionConfig(BaseModel):
    thresholds: dict[str, ThresholdRule] = Field(default_factory=dict)
    top_k: TopKRule | None = None
    correlation: CorrelationRule | None = None
    hysteresis: HysteresisRule | None = None


class Policy(BaseModel):
    thresholds: dict[str, ThresholdRule] = Field(default_factory=dict)
    top_k: TopKRule | None = None
    correlation: CorrelationRule | None = None
    hysteresis: HysteresisRule | None = None
    selection: SelectionConfig | None = None
    validation_profiles: dict[str, ValidationProfile] = Field(default_factory=dict)
    default_profile_by_stage: dict[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:  # type: ignore[override]
        self._normalize_selection()

    def _normalize_selection(self) -> None:
        selection = self.selection or SelectionConfig()
        merged_thresholds = dict(selection.thresholds)
        merged_thresholds.update(self.thresholds)

        top_k = selection.top_k or self.top_k
        correlation = selection.correlation or self.correlation
        hysteresis = selection.hysteresis or self.hysteresis

        self.selection = SelectionConfig(
            thresholds=merged_thresholds,
            top_k=top_k,
            correlation=correlation,
            hysteresis=hysteresis,
        )
        self.thresholds = merged_thresholds
        self.top_k = top_k
        self.correlation = correlation
        self.hysteresis = hysteresis


def parse_policy(raw: str | bytes | dict) -> Policy:
    """Parse a policy from YAML/JSON string or pre-parsed dict."""
    data: dict
    if isinstance(raw, (str, bytes)):
        data = yaml.safe_load(raw)
    else:
        data = raw
    return Policy.model_validate(data)


def _normalize_key(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower().replace("-", "_")


def _choose_profile(policy: Policy, stage: str | None, profile: str | None) -> str | None:
    if not policy.validation_profiles:
        return None

    profiles = policy.validation_profiles
    normalized_profiles: Dict[str, str] = {_normalize_key(name) or "": name for name in profiles}

    def resolve(candidate: str | None) -> str | None:
        normalized = _normalize_key(candidate)
        if normalized and normalized in normalized_profiles:
            return normalized_profiles[normalized]
        return None

    selected = resolve(profile)
    if selected:
        return selected

    normalized_stage = _normalize_key(stage)
    if normalized_stage:
        mapping = {_normalize_key(k) or "": v for k, v in policy.default_profile_by_stage.items()}
        for key in (normalized_stage, f"{normalized_stage}_only"):
            mapped = mapping.get(key)
            selected = resolve(mapped)
            if selected:
                return selected
        selected = resolve(stage)
        if selected:
            return selected

    for mapped in policy.default_profile_by_stage.values():
        selected = resolve(mapped)
        if selected:
            return selected

    if "backtest" in normalized_profiles:
        return normalized_profiles["backtest"]
    if "paper" in normalized_profiles:
        return normalized_profiles["paper"]

    return next(iter(profiles.keys()))


def _materialize_policy(policy: Policy, *, stage: str | None, profile: str | None) -> tuple[Policy, str | None]:
    """Return an evaluatable Policy and the profile name applied."""
    selected_profile = _choose_profile(policy, stage, profile)

    selection = policy.selection or SelectionConfig()
    thresholds = dict(selection.thresholds)
    if selected_profile:
        profile_cfg = policy.validation_profiles.get(selected_profile)
        if profile_cfg:
            thresholds.update(profile_cfg.to_thresholds())

    resolved_policy = Policy(
        thresholds=thresholds,
        top_k=selection.top_k,
        correlation=selection.correlation,
        hysteresis=selection.hysteresis,
    )
    return resolved_policy, selected_profile


def _apply_thresholds(metrics: Dict[str, Dict[str, float]], policy: Policy) -> List[str]:
    """Legacy thresholds helper retained for compatibility."""
    result: List[str] = []
    for sid, vals in metrics.items():
        ok = True
        for rule in policy.thresholds.values():
            v = vals.get(rule.metric)
            if v is None:
                ok = False
                break
            if rule.min is not None and v < rule.min:
                ok = False
                break
            if rule.max is not None and v > rule.max:
                ok = False
                break
        if ok:
            result.append(sid)
    return result


def _apply_topk(metrics: Dict[str, Dict[str, float]], candidates: Iterable[str], rule: TopKRule) -> List[str]:
    scored = [(sid, metrics.get(sid, {}).get(rule.metric, -math.inf)) for sid in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [sid for sid, _ in scored[: rule.k]]


def _apply_correlation(
    correlations: Dict[Tuple[str, str], float] | None,
    candidates: Iterable[str],
    rule: CorrelationRule,
) -> List[str]:
    if not correlations:
        return list(candidates)
    selected: List[str] = []
    for sid in candidates:
        if all(
            abs(correlations.get((sid, other) if sid <= other else (other, sid), 0.0)) <= rule.max
            for other in selected
        ):
            selected.append(sid)
    return selected


def _apply_hysteresis(
    metrics: Dict[str, Dict[str, float]],
    candidates: Iterable[str],
    prev_active: Iterable[str] | None,
    rule: HysteresisRule,
) -> List[str]:
    prev = set(prev_active or [])
    result: List[str] = []
    for sid in candidates:
        val = metrics.get(sid, {}).get(rule.metric)
        if val is None:
            continue
        if sid in prev:
            if val >= rule.exit:
                result.append(sid)
        else:
            if val >= rule.enter:
                result.append(sid)
    return result


def evaluate_policy(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    prev_active: Iterable[str] | None = None,
    correlations: Dict[Tuple[str, str], float] | None = None,
    *,
    stage: str | None = None,
    profile: str | None = None,
) -> PolicyEvaluationResult:
    """Return strategy ids that satisfy the policy and detailed rule results.

    Args:
        metrics: per-strategy metric mapping.
        policy: policy definition, potentially with validation profiles.
        prev_active: previously active strategies for hysteresis.
        correlations: optional pairwise correlation matrix keyed by tuple(sorted((a,b))).
        stage: optional evaluation stage (e.g., backtest/paper) used to pick a validation profile.
        profile: explicit validation profile override.
    """
    resolved_policy, selected_profile = _materialize_policy(policy, stage=stage, profile=profile)
    normalized = _normalize_metrics(metrics)
    threshold_passed, threshold_failures = _evaluate_thresholds_with_details(normalized, resolved_policy.thresholds)

    candidates = threshold_passed
    topk_ranks: Dict[str, int] = {sid: idx for idx, sid in enumerate(candidates)}
    if resolved_policy.top_k:
        candidates, topk_ranks = _apply_topk_with_details(normalized, candidates, resolved_policy.top_k)
    topk_selected = set(candidates)

    correlation_violations: Dict[str, List[Tuple[str, float]]] = {}
    if resolved_policy.correlation:
        candidates, correlation_violations = _apply_correlation_with_details(
            correlations, candidates, resolved_policy.correlation
        )

    hysteresis_blocked: Dict[str, str] = {}
    if resolved_policy.hysteresis:
        candidates, hysteresis_blocked = _apply_hysteresis_with_details(
            normalized, candidates, prev_active, resolved_policy.hysteresis
        )

    selected_ids = list(candidates)

    grouped_thresholds = _group_thresholds(resolved_policy.thresholds)
    rules: List[ValidationRule] = [
        DataCurrencyRule(required_metrics=[t.metric for t in grouped_thresholds["data_currency"]]),
        SampleRule(thresholds=grouped_thresholds["sample"]),
        PerformanceRule(
            thresholds=grouped_thresholds["performance"] or list(resolved_policy.thresholds.values()),
            threshold_failures=threshold_failures,
            top_k=resolved_policy.top_k,
            topk_selected=topk_selected,
            topk_ranks=topk_ranks,
        ),
        RiskConstraintRule(
            correlation_rule=resolved_policy.correlation,
            hysteresis_rule=resolved_policy.hysteresis,
            correlation_violations=correlation_violations,
            hysteresis_blocked=hysteresis_blocked,
        ),
    ]

    rule_results: Dict[str, Dict[str, RuleResult]] = {}
    previous = set(prev_active or [])
    for strategy_id, strategy_metrics in normalized.items():
        context = RuleContext(
            strategy_id=strategy_id,
            previous_active=previous,
            correlations=correlations,
        )
        per_rule: Dict[str, RuleResult] = {}
        for rule in rules:
            per_rule[rule.name] = rule.evaluate(strategy_metrics, context)
        rule_results[strategy_id] = per_rule

    return PolicyEvaluationResult(
        selected_ids=selected_ids,
        rule_results=rule_results,
        profile=selected_profile,
    )


def _group_thresholds(thresholds: Mapping[str, ThresholdRule]) -> Dict[str, List[ThresholdRule]]:
    grouped: Dict[str, List[ThresholdRule]] = {
        "data_currency": [],
        "sample": [],
        "performance": [],
        "risk": [],
    }
    for rule in thresholds.values():
        group = _classify_metric(rule.metric)
        grouped[group].append(rule)
    return grouped


def _classify_metric(metric: str) -> str:
    name = metric.lower()
    if name.startswith(("lag", "stale", "fresh", "as_of", "coverage")):
        return "data_currency"
    if name.startswith(("sample", "history", "effective_history", "n_trades", "num_trades")) or "trade" in name:
        return "sample"
    if name.startswith(
        (
            "adv_",
            "participation_rate",
            "exposure",
            "var",
            "es",
            "beta",
            "correlation",
            "leverage",
            "tail",
        )
    ):
        return "risk"
    return "performance"


def _evaluate_thresholds_with_details(
    metrics: Mapping[str, Mapping[str, float]],
    thresholds: Mapping[str, ThresholdRule],
) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]]]:
    passed: List[str] = []
    failures: Dict[str, List[Dict[str, Any]]] = {}

    for sid, values in metrics.items():
        strategy_failures: List[Dict[str, Any]] = []
        for rule in thresholds.values():
            val = values.get(rule.metric)
            if val is None:
                strategy_failures.append(
                    {"metric": rule.metric, "reason": "missing_metric"}
                )
                continue
            if rule.min is not None and val < rule.min:
                strategy_failures.append(
                    {
                        "metric": rule.metric,
                        "reason": "below_min",
                        "min": rule.min,
                        "value": val,
                    }
                )
            if rule.max is not None and val > rule.max:
                strategy_failures.append(
                    {
                        "metric": rule.metric,
                        "reason": "above_max",
                        "max": rule.max,
                        "value": val,
                    }
                )
        if strategy_failures:
            failures[sid] = strategy_failures
        else:
            passed.append(sid)
    return passed, failures


def _apply_topk_with_details(
    metrics: Dict[str, Dict[str, float]],
    candidates: Iterable[str],
    rule: TopKRule,
) -> Tuple[List[str], Dict[str, int]]:
    scored = [(sid, metrics.get(sid, {}).get(rule.metric, -math.inf)) for sid in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = [sid for sid, _ in scored[: rule.k]]
    ranks: Dict[str, int] = {sid: idx for idx, (sid, _) in enumerate(scored)}
    return selected, ranks


def _apply_correlation_with_details(
    correlations: Dict[Tuple[str, str], float] | None,
    candidates: Iterable[str],
    rule: CorrelationRule,
) -> Tuple[List[str], Dict[str, List[Tuple[str, float]]]]:
    if not correlations:
        return list(candidates), {}
    selected: List[str] = []
    violations: Dict[str, List[Tuple[str, float]]] = {}
    for sid in candidates:
        blocked_by: List[Tuple[str, float]] = []
        for other in selected:
            corr = correlations.get((sid, other) if sid <= other else (other, sid), 0.0)
            if abs(corr) > rule.max:
                blocked_by.append((other, corr))
        if blocked_by:
            violations[sid] = blocked_by
            continue
        selected.append(sid)
    return selected, violations


def _apply_hysteresis_with_details(
    metrics: Dict[str, Dict[str, float]],
    candidates: Iterable[str],
    prev_active: Iterable[str] | None,
    rule: HysteresisRule,
) -> Tuple[List[str], Dict[str, str]]:
    prev = set(prev_active or [])
    result: List[str] = []
    blocked: Dict[str, str] = {}
    for sid in candidates:
        val = metrics.get(sid, {}).get(rule.metric)
        if val is None:
            continue
        if sid in prev:
            if val >= rule.exit:
                result.append(sid)
            else:
                blocked[sid] = "exit"
        else:
            if val >= rule.enter:
                result.append(sid)
            else:
                blocked[sid] = "enter"
    return result, blocked


@dataclass
class DataCurrencyRule:
    required_metrics: Sequence[str] | None = None
    name: str = "data_currency"
    severity: str = "blocking"
    owner: str = "ops"
    tags: Sequence[str] = ("data_currency",)

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        missing: List[str] = []
        required = list(self.required_metrics or [])
        if required:
            missing = [metric for metric in required if metric not in metrics]
        status = "pass"
        reason_code = "data_currency_ok"
        reason = "Required metrics present"
        if not metrics:
            status = "fail"
            reason_code = "metrics_missing"
            reason = "No metrics provided for strategy"
        elif missing:
            status = "fail"
            reason_code = "missing_metric"
            reason = f"Missing metrics: {', '.join(sorted(missing))}"
        details = {
            "missing_metrics": missing,
            "available_metrics": sorted(metrics.keys()),
        }
        return RuleResult(
            status=status,
            severity=self.severity,
            owner=self.owner,
            reason_code=reason_code,
            reason=reason,
            tags=list(self.tags),
            details=details,
        )


@dataclass
class SampleRule:
    thresholds: Sequence[ThresholdRule] = field(default_factory=list)
    name: str = "sample"
    severity: str = "soft"
    owner: str = "quant"
    tags: Sequence[str] = ("sample",)

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        sample_metrics = {
            key: value
            for key, value in metrics.items()
            if key in {"n_trades_total", "n_trades_per_year", "num_trades", "effective_history_years", "sample_days"}
        }
        if self.thresholds:
            _, failures = _evaluate_thresholds_with_details({"_": sample_metrics}, {t.metric: t for t in self.thresholds})
            if failures:
                detail = failures.get("_", [])
                reason = f"Sample thresholds failed: {', '.join(item['metric'] for item in detail)}"
                return RuleResult(
                    status="fail",
                    severity=self.severity,
                    owner=self.owner,
                    reason_code="sample_thresholds_failed",
                    reason=reason,
                    tags=list(self.tags),
                    details={"violations": detail},
                )

        if sample_metrics and any(value is not None and value > 0 for value in sample_metrics.values()):
            return RuleResult(
                status="pass",
                severity=self.severity,
                owner=self.owner,
                reason_code="sample_ok",
                reason="Sample depth present",
                tags=list(self.tags),
                details={"sample_metrics": sample_metrics},
            )

        return RuleResult(
            status="warn",
            severity=self.severity,
            owner=self.owner,
            reason_code="sample_metrics_missing",
            reason="No sample metrics found",
            tags=list(self.tags),
            details={"sample_metrics": sample_metrics},
        )


@dataclass
class PerformanceRule:
    thresholds: Sequence[ThresholdRule]
    threshold_failures: Dict[str, List[Dict[str, Any]]]
    top_k: TopKRule | None
    topk_selected: set[str]
    topk_ranks: Dict[str, int]
    name: str = "performance"
    severity: str = "blocking"
    owner: str = "quant"
    tags: Sequence[str] = ("performance", "thresholds")

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        sid = context.strategy_id
        failures = self.threshold_failures.get(sid, [])
        if failures:
            reason = self._format_failure_reason(failures[0])
            return RuleResult(
                status="fail",
                severity=self.severity,
                owner=self.owner,
                reason_code="performance_thresholds_failed",
                reason=reason,
                tags=list(self.tags),
                details={"violations": failures},
            )

        if self.top_k and sid not in self.topk_selected:
            rank = self.topk_ranks.get(sid)
            reason = (
                f"Rank {rank + 1} outside top_k={self.top_k.k}"
                if rank is not None
                else f"Not selected by top_k={self.top_k.k}"
            )
            return RuleResult(
                status="fail",
                severity=self.severity,
                owner=self.owner,
                reason_code="performance_rank_outside_top_k",
                reason=reason,
                tags=list(set(self.tags) | {"top_k"}),
                details={"rank": rank, "top_k": self.top_k.k},
            )

        return RuleResult(
            status="pass",
            severity=self.severity,
            owner=self.owner,
            reason_code="performance_ok",
            reason="Passed thresholds and ranking",
            tags=list(self.tags),
            details={
                "rank": self.topk_ranks.get(sid),
                "top_k": self.top_k.k if self.top_k else None,
            },
        )

    @staticmethod
    def _format_failure_reason(failure: Dict[str, Any]) -> str:
        metric = failure.get("metric", "unknown")
        reason = failure.get("reason", "threshold_failed")
        if reason == "below_min":
            return f"{metric} below minimum {failure.get('min')}"
        if reason == "above_max":
            return f"{metric} above maximum {failure.get('max')}"
        if reason == "missing_metric":
            return f"{metric} missing"
        return f"{metric} failed"


@dataclass
class RiskConstraintRule:
    correlation_rule: CorrelationRule | None
    hysteresis_rule: HysteresisRule | None
    correlation_violations: Dict[str, List[Tuple[str, float]]] = field(default_factory=dict)
    hysteresis_blocked: Dict[str, str] = field(default_factory=dict)
    name: str = "risk_constraint"
    severity: str = "blocking"
    owner: str = "risk"
    tags: Sequence[str] = ("risk",)

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        sid = context.strategy_id
        if self.correlation_rule and sid in self.correlation_violations:
            blocked = [
                {"strategy_id": other, "correlation": corr}
                for other, corr in self.correlation_violations[sid]
            ]
            return RuleResult(
                status="fail",
                severity=self.severity,
                owner=self.owner,
                reason_code="correlation_constraint_failed",
                reason=f"Correlation exceeds max {self.correlation_rule.max}",
                tags=list(self.tags),
                details={"blocked_by": blocked},
            )

        if self.hysteresis_rule and sid in self.hysteresis_blocked:
            mode = self.hysteresis_blocked.get(sid)
            reason_code = "hysteresis_exit" if mode == "exit" else "hysteresis_not_entered"
            reason = (
                f"{self.hysteresis_rule.metric} below exit {self.hysteresis_rule.exit} "
                f"for previously active strategy"
                if mode == "exit"
                else f"{self.hysteresis_rule.metric} below enter {self.hysteresis_rule.enter}"
            )
            return RuleResult(
                status="fail",
                severity=self.severity,
                owner=self.owner,
                reason_code=reason_code,
                reason=reason,
                tags=list(self.tags),
                details={
                    "metric": self.hysteresis_rule.metric,
                    "previously_active": sid in set(context.previous_active or []),
                    "mode": mode,
                    "value": metrics.get(self.hysteresis_rule.metric),
                },
            )

        if not self.correlation_rule and not self.hysteresis_rule:
            return RuleResult(
                status="pass",
                severity="info",
                owner=self.owner,
                reason_code="risk_constraints_not_configured",
                reason="No risk constraints configured",
                tags=list(self.tags),
                details={},
            )

        return RuleResult(
            status="pass",
            severity=self.severity,
            owner=self.owner,
            reason_code="risk_constraints_ok",
            reason="Risk constraints satisfied",
            tags=list(self.tags),
            details={},
        )


__all__ = [
    "Policy",
    "PolicyEvaluationResult",
    "SelectionConfig",
    "ValidationProfile",
    "SampleProfile",
    "PerformanceProfile",
    "RobustnessProfile",
    "RiskProfile",
    "ValidationRule",
    "RuleContext",
    "RuleResult",
    "ThresholdRule",
    "TopKRule",
    "CorrelationRule",
    "HysteresisRule",
    "DataCurrencyRule",
    "SampleRule",
    "PerformanceRule",
    "RiskConstraintRule",
    "parse_policy",
    "evaluate_policy",
]
