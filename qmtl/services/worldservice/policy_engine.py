from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
import statistics
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Protocol, Sequence, Tuple

import yaml
from pydantic import BaseModel, Field
from qmtl.foundation.common.hashutils import hash_bytes


def _flatten_metrics(values: Mapping[str, Any] | None) -> Dict[str, float]:
    """Flatten nested metric payloads into a simple name -> float mapping (dot paths)."""
    flat: Dict[str, float] = {}

    def visit(path: list[str], obj: Any) -> None:
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                visit(path + [str(k)], v)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            name = path[-1]
            dotted = ".".join(path)
            flat.setdefault(name, float(obj))
            flat.setdefault(dotted, float(obj))

    if values:
        visit([], values)
    return flat


def _normalize_metrics(metrics: Mapping[str, Mapping[str, Any]] | None) -> Dict[str, Dict[str, float]]:
    """Normalize raw metrics to a per-strategy flat mapping."""
    normalized: Dict[str, Dict[str, float]] = {}
    if not metrics:
        return normalized
    for strategy_id, values in metrics.items():
        normalized[strategy_id] = _flatten_metrics(values)
    return normalized


def _flatten_evaluation_metrics(metrics: Mapping[str, Any] | None) -> Dict[str, float]:
    """Flatten EvaluationRun.metrics-style payload into a simple metric map."""
    if not metrics:
        return {}
    flat = _flatten_metrics(metrics)
    return _augment_extended_metric_derivatives(flat)


def _augment_extended_metric_derivatives(flat: Dict[str, float]) -> Dict[str, float]:
    """Derive helpful extended metrics (live vs backtest decay, live drawdown) when possible."""
    out = dict(flat)
    live_sharpe = out.get("live_sharpe")
    backtest_sharpe = out.get("sharpe")
    if live_sharpe is not None and backtest_sharpe not in (None, 0):
        out.setdefault("live_vs_backtest_sharpe_ratio", live_sharpe / backtest_sharpe)

    live_dd = out.get("live_max_drawdown")
    backtest_dd = out.get("max_drawdown")
    if live_dd is not None:
        out.setdefault("live_dd", live_dd)
    if live_dd is not None and backtest_dd not in (None, 0):
        out.setdefault("live_vs_backtest_dd_ratio", live_dd / backtest_dd if backtest_dd else None)
    return out


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
    ruleset_hash: str | None = None
    policy_version: str | None = None
    recommended_stage: str | None = None

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
    severity: str | None = None
    owner: str | None = None

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
    severity: str | None = None
    owner: str | None = None

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
    cv_sharpe_gap_max: float | None = None  # v1.5+ train/test gap
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
    severity: str | None = None
    owner: str | None = None

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


class CohortRuleConfig(BaseModel):
    """Configuration for cohort-level rules (campaign-wide)."""

    sharpe_median_min: float | None = None
    dsr_median_min: float | None = None
    top_k: int | None = None
    severity: str | None = None
    owner: str | None = None


class PortfolioRuleConfig(BaseModel):
    """Configuration for portfolio-level incremental risk/impact rules."""

    max_incremental_var_99: float | None = None
    max_incremental_es_99: float | None = None
    min_portfolio_sharpe_uplift: float | None = None
    severity: str | None = None
    owner: str | None = None


class StressRuleConfig(BaseModel):
    """Configuration for stress-scenario based validation."""

    scenarios: Dict[str, Dict[str, float]] | None = None
    severity: str | None = None
    owner: str | None = None


class LiveMonitoringConfig(BaseModel):
    """Configuration for ongoing live monitoring validation."""

    lookback_days: int | None = None
    decay_threshold: float | None = None
    sharpe_min: float | None = None
    dd_max: float | None = None
    severity: str | None = None
    owner: str | None = None


class ValidationConfig(BaseModel):
    """Global validation error handling configuration (§7.4 of validation architecture doc)."""

    on_error: str = Field(default="fail", pattern="^(fail|warn)$")
    on_missing_metric: str = Field(default="fail", pattern="^(fail|warn|ignore)$")


class Policy(BaseModel):
    thresholds: dict[str, ThresholdRule] = Field(default_factory=dict)
    top_k: TopKRule | None = None
    correlation: CorrelationRule | None = None
    hysteresis: HysteresisRule | None = None
    selection: SelectionConfig | None = None
    validation_profiles: dict[str, ValidationProfile] = Field(default_factory=dict)
    default_profile_by_stage: dict[str, str] = Field(default_factory=dict)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    cohort: CohortRuleConfig | None = None
    portfolio: PortfolioRuleConfig | None = None
    stress: StressRuleConfig | None = None
    live_monitoring: LiveMonitoringConfig | None = None

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


_PROFILE_TO_STAGE: Dict[str, str] = {
    "backtest": "backtest_only",
    "paper": "paper_only",
    "live": "paper_ok_live_candidate",
}
_STAGE_TO_STAGE: Dict[str, str] = {
    "backtest": "backtest_only",
    "paper": "paper_only",
    "live": "paper_ok_live_candidate",
    "backtest_only": "backtest_only",
    "paper_only": "paper_only",
    "paper_ok_live_candidate": "paper_ok_live_candidate",
}


def recommended_stage(profile: str | None, stage: str | None) -> str | None:
    """Derive a recommended stage from validation profile or explicit stage."""

    normalized_stage = _normalize_key(stage)
    if normalized_stage in _STAGE_TO_STAGE:
        return _STAGE_TO_STAGE[normalized_stage]

    normalized_profile = _normalize_key(profile)
    if normalized_profile in _PROFILE_TO_STAGE:
        return _PROFILE_TO_STAGE[normalized_profile]

    return None


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


def _materialize_policy(policy: Policy, *, stage: str | None, profile: str | None) -> tuple[Policy, str | None, ValidationProfile | None]:
    """Return an evaluatable Policy, applied profile name, and profile config."""
    selected_profile = _choose_profile(policy, stage, profile)
    selected_profile_cfg = policy.validation_profiles.get(selected_profile) if selected_profile else None

    selection = policy.selection or SelectionConfig()
    thresholds = dict(selection.thresholds)
    if selected_profile:
        profile_cfg = selected_profile_cfg
        if profile_cfg:
            thresholds.update(profile_cfg.to_thresholds())

    resolved_policy = Policy(
        thresholds=thresholds,
        top_k=selection.top_k,
        correlation=selection.correlation,
        hysteresis=selection.hysteresis,
        cohort=policy.cohort,
        portfolio=policy.portfolio,
        stress=policy.stress,
        live_monitoring=policy.live_monitoring,
        validation=policy.validation,
    )
    return resolved_policy, selected_profile, selected_profile_cfg


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


def _ruleset_hash(policy: Policy, *, profile: str | None) -> str:
    payload = {"policy": policy.model_dump(mode="json", exclude_none=True)}
    if profile:
        payload["profile"] = profile
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"blake3:{hash_bytes(serialized.encode('utf-8'))}"


def _resolve_meta_defaults(cfg: Any, *, default_severity: str, default_owner: str) -> tuple[str, str]:
    severity = getattr(cfg, "severity", None) or default_severity
    owner = getattr(cfg, "owner", None) or default_owner
    return severity, owner


def _stub_rule_result(
    *,
    name: str,
    severity: str | None,
    owner: str | None,
    tag: str,
    reason_code: str,
    reason: str,
    details: Dict[str, Any],
) -> RuleResult:
    return RuleResult(
        status="warn",
        severity=severity or "info",
        owner=owner or "ops",
        reason_code=reason_code,
        reason=reason,
        tags=[tag],
        details=details,
    )


def evaluate_cohort_rules(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> Dict[str, RuleResult]:
    """Evaluate cohort-level rules across strategies."""
    cfg = policy.cohort
    if cfg is None:
        return {}
    severity, owner = _resolve_meta_defaults(cfg, default_severity="soft", default_owner="risk")
    sharpe_values = [v.get("sharpe") for v in metrics.values() if isinstance(v.get("sharpe"), (int, float))]
    dsr_values = [v.get("deflated_sharpe_ratio") for v in metrics.values() if isinstance(v.get("deflated_sharpe_ratio"), (int, float))]

    median_sharpe = statistics.median(sharpe_values) if sharpe_values else None
    median_dsr = statistics.median(dsr_values) if dsr_values else None

    topk_selected: set[str] = set()
    if cfg.top_k and sharpe_values:
        ranked = sorted(metrics.items(), key=lambda item: item[1].get("sharpe", float("-inf")), reverse=True)
        topk_selected = {sid for sid, _ in ranked[: cfg.top_k]}

    results: Dict[str, RuleResult] = {}
    for sid, vals in metrics.items():
        reasons: list[str] = []
        tags = ["cohort"]
        status = "pass"
        details: Dict[str, Any] = {
            "median_sharpe": median_sharpe,
            "median_dsr": median_dsr,
            "top_k": cfg.top_k,
            "selected_in_top_k": sid in topk_selected if topk_selected else None,
            "sharpe": vals.get("sharpe"),
            "deflated_sharpe_ratio": vals.get("deflated_sharpe_ratio"),
        }

        if cfg.sharpe_median_min is not None:
            if median_sharpe is None:
                status = "warn"
                reasons.append("median_sharpe_missing")
            elif median_sharpe < cfg.sharpe_median_min:
                status = "fail"
                reasons.append("cohort_median_sharpe_below_min")
                details["sharpe_median_min"] = cfg.sharpe_median_min

        if cfg.dsr_median_min is not None:
            if median_dsr is None:
                status = "warn"
                reasons.append("median_dsr_missing")
            elif median_dsr < cfg.dsr_median_min:
                status = "fail"
                reasons.append("cohort_median_dsr_below_min")
                details["dsr_median_min"] = cfg.dsr_median_min

        if cfg.top_k:
            if not topk_selected:
                status = "warn"
                reasons.append("top_k_unavailable")
            elif sid not in topk_selected:
                status = "fail"
                reasons.append("cohort_top_k_exceeded")

        reason_code = reasons[0] if reasons else "cohort_ok"
        reason = ", ".join(reasons) if reasons else "Cohort criteria satisfied"
        results[sid] = RuleResult(
            status=status,
            severity=severity,
            owner=owner,
            reason_code=reason_code,
            reason=reason,
            tags=tags,
            details=details,
        )
    return results


def evaluate_portfolio_rules(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> Dict[str, RuleResult]:
    """Evaluate portfolio-level incremental risk/impact rules against provided metrics."""
    cfg = policy.portfolio
    if cfg is None:
        return {}
    severity, owner = _resolve_meta_defaults(cfg, default_severity="soft", default_owner="risk")
    results: Dict[str, RuleResult] = {}
    for sid, vals in metrics.items():
        reasons: list[str] = []
        status = "pass"
        details: Dict[str, Any] = {
            "max_incremental_var_99": vals.get("incremental_var_99"),
            "max_incremental_es_99": vals.get("incremental_es_99"),
            "portfolio_sharpe_uplift": vals.get("portfolio_sharpe_uplift"),
        }

        if cfg.max_incremental_var_99 is not None:
            value = vals.get("incremental_var_99")
            if value is None:
                status = "warn"
                reasons.append("incremental_var_missing")
            elif value > cfg.max_incremental_var_99:
                status = "fail"
                reasons.append("incremental_var_exceeds_max")
                details["incremental_var_99_max"] = cfg.max_incremental_var_99

        if cfg.max_incremental_es_99 is not None:
            value = vals.get("incremental_es_99")
            if value is None:
                status = "warn"
                reasons.append("incremental_es_missing")
            elif value > cfg.max_incremental_es_99:
                status = "fail"
                reasons.append("incremental_es_exceeds_max")
                details["incremental_es_99_max"] = cfg.max_incremental_es_99

        if cfg.min_portfolio_sharpe_uplift is not None:
            value = vals.get("portfolio_sharpe_uplift")
            if value is None:
                status = "warn"
                reasons.append("portfolio_sharpe_uplift_missing")
            elif value < cfg.min_portfolio_sharpe_uplift:
                status = "fail"
                reasons.append("portfolio_sharpe_uplift_below_min")
                details["min_portfolio_sharpe_uplift"] = cfg.min_portfolio_sharpe_uplift

        reason_code = reasons[0] if reasons else "portfolio_ok"
        reason = ", ".join(reasons) if reasons else "Portfolio constraints satisfied"
        results[sid] = RuleResult(
            status=status,
            severity=severity,
            owner=owner,
            reason_code=reason_code,
            reason=reason,
            tags=["portfolio"],
            details=details,
        )
    return results


def evaluate_stress_rules(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> Dict[str, RuleResult]:
    """Evaluate stress-scenario rules if stress metrics are provided."""
    cfg = policy.stress
    if cfg is None:
        return {}
    severity, owner = _resolve_meta_defaults(cfg, default_severity="info", default_owner="ops")
    scenarios = cfg.scenarios or {}
    results: Dict[str, RuleResult] = {}
    for sid, vals in metrics.items():
        status = "pass"
        reasons: list[str] = []
        details: Dict[str, Any] = {"scenarios": list(scenarios.keys()), "stage": stage}

        for name, thresholds in scenarios.items():
            dd_max = thresholds.get("dd_max")
            es_99_max = thresholds.get("es_99")
            var_99_max = thresholds.get("var_99")
            metric_prefix = f"stress.{name}."
            dd = vals.get(f"{metric_prefix}max_drawdown") or vals.get(f"{metric_prefix}dd_max")
            es = vals.get(f"{metric_prefix}es_99")
            var = vals.get(f"{metric_prefix}var_99")

            if dd_max is not None:
                if dd is None:
                    status = "warn"
                    reasons.append(f"{name}_dd_missing")
                elif dd > dd_max:
                    status = "fail"
                    reasons.append(f"{name}_dd_exceeds_max")
                    details[f"{name}_dd_max"] = dd_max
            if es_99_max is not None:
                if es is None:
                    status = "warn"
                    reasons.append(f"{name}_es_missing")
                elif es > es_99_max:
                    status = "fail"
                    reasons.append(f"{name}_es_exceeds_max")
                    details[f"{name}_es_99_max"] = es_99_max
            if var_99_max is not None:
                if var is None:
                    status = "warn"
                    reasons.append(f"{name}_var_missing")
                elif var > var_99_max:
                    status = "fail"
                    reasons.append(f"{name}_var_exceeds_max")
                    details[f"{name}_var_99_max"] = var_99_max

        reason_code = reasons[0] if reasons else "stress_ok"
        reason = ", ".join(reasons) if reasons else "Stress scenarios satisfied"
        results[sid] = RuleResult(
            status=status,
            severity=severity,
            owner=owner,
            reason_code=reason_code,
            reason=reason,
            tags=["stress"],
            details=details,
        )
    return results


def evaluate_live_monitoring(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> RuleResult | None:
    """Evaluate live monitoring guardrails using realized/live metrics if present."""
    cfg = policy.live_monitoring
    if cfg is None:
        return None
    severity, owner = _resolve_meta_defaults(cfg, default_severity="soft", default_owner="risk")
    sharpe_min = cfg.sharpe_min
    dd_max = cfg.dd_max
    decay_threshold = cfg.decay_threshold
    lookback = cfg.lookback_days

    # Aggregate across strategies; use average realized Sharpe/DD if present
    sharpe_values: list[float] = []
    dd_values: list[float] = []
    decay_values: list[float] = []
    for vals in metrics.values():
        sharpe_live = vals.get("live_sharpe") or vals.get("realized_sharpe")
        dd_live = vals.get("live_max_drawdown") or vals.get("realized_max_drawdown")
        decay = vals.get("live_vs_backtest_sharpe_ratio")
        if isinstance(sharpe_live, (int, float)):
            sharpe_values.append(float(sharpe_live))
        if isinstance(dd_live, (int, float)):
            dd_values.append(float(dd_live))
        if isinstance(decay, (int, float)):
            decay_values.append(float(decay))

    reasons: list[str] = []
    status = "pass"
    details: Dict[str, Any] = {
        "sharpe_mean": statistics.mean(sharpe_values) if sharpe_values else None,
        "dd_mean": statistics.mean(dd_values) if dd_values else None,
        "decay_mean": statistics.mean(decay_values) if decay_values else None,
        "lookback_days": lookback,
    }

    if sharpe_min is not None:
        if not sharpe_values:
            status = "warn"
            reasons.append("live_sharpe_missing")
        elif details["sharpe_mean"] < sharpe_min:
            status = "fail"
            reasons.append("live_sharpe_below_min")
            details["sharpe_min"] = sharpe_min

    if dd_max is not None:
        if not dd_values:
            status = "warn"
            reasons.append("live_dd_missing")
        elif details["dd_mean"] > dd_max:
            status = "fail"
            reasons.append("live_dd_exceeds_max")
            details["dd_max"] = dd_max

    if decay_threshold is not None:
        if not decay_values:
            status = "warn"
            reasons.append("live_decay_missing")
        elif details["decay_mean"] < decay_threshold:
            status = "fail"
            reasons.append("live_decay_below_threshold")
            details["decay_threshold"] = decay_threshold

    reason_code = reasons[0] if reasons else "live_monitoring_ok"
    reason = ", ".join(reasons) if reasons else "Live monitoring within thresholds"
    return RuleResult(
        status=status,
        severity=severity,
        owner=owner,
        reason_code=reason_code,
        reason=reason,
        tags=["live_monitoring"],
        details=details,
    )


def evaluate_policy(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    prev_active: Iterable[str] | None = None,
    correlations: Dict[Tuple[str, str], float] | None = None,
    *,
    stage: str | None = None,
    profile: str | None = None,
    policy_version: str | int | None = None,
) -> PolicyEvaluationResult:
    """Return strategy ids that satisfy the policy and detailed rule results.

    Args:
        metrics: per-strategy metric mapping.
        policy: policy definition, potentially with validation profiles.
        prev_active: previously active strategies for hysteresis.
        correlations: optional pairwise correlation matrix keyed by tuple(sorted((a,b))).
        stage: optional evaluation stage (e.g., backtest/paper) used to pick a validation profile.
        profile: explicit validation profile override.
        policy_version: optional version identifier for the evaluated policy.
    """
    resolved_policy, selected_profile, selected_profile_cfg = _materialize_policy(
        policy, stage=stage, profile=profile
    )
    validation_cfg = resolved_policy.validation or ValidationConfig()
    normalized = _normalize_metrics(metrics)
    threshold_passed, threshold_failures = _evaluate_thresholds_with_details(
        normalized,
        resolved_policy.thresholds,
        missing_mode=validation_cfg.on_missing_metric,
    )

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
    sample_severity = (selected_profile_cfg.sample.severity if selected_profile_cfg and selected_profile_cfg.sample else None) or "soft"
    sample_owner = (selected_profile_cfg.sample.owner if selected_profile_cfg and selected_profile_cfg.sample else None) or "quant"
    performance_severity = (
        selected_profile_cfg.performance.severity if selected_profile_cfg and selected_profile_cfg.performance else None
    ) or "blocking"
    performance_owner = (
        selected_profile_cfg.performance.owner if selected_profile_cfg and selected_profile_cfg.performance else None
    ) or "quant"
    risk_severity = (selected_profile_cfg.risk.severity if selected_profile_cfg and selected_profile_cfg.risk else None) or "blocking"
    risk_owner = (selected_profile_cfg.risk.owner if selected_profile_cfg and selected_profile_cfg.risk else None) or "risk"
    robustness_severity = (
        selected_profile_cfg.robustness.severity if selected_profile_cfg and selected_profile_cfg.robustness else None
    ) or "soft"
    robustness_owner = (
        selected_profile_cfg.robustness.owner if selected_profile_cfg and selected_profile_cfg.robustness else None
    ) or "quant"
    robustness_dsr_min = (
        selected_profile_cfg.robustness.dsr_min if selected_profile_cfg and selected_profile_cfg.robustness else None
    )
    robustness_cv_sharpe_gap_max = (
        selected_profile_cfg.robustness.cv_sharpe_gap_max if selected_profile_cfg and selected_profile_cfg.robustness else None
    )

    rules: List[ValidationRule] = [
        DataCurrencyRule(
            required_metrics=[t.metric for t in grouped_thresholds["data_currency"]],
            on_missing_metric=validation_cfg.on_missing_metric,
        ),
        SampleRule(
            thresholds=grouped_thresholds["sample"],
            severity=sample_severity,
            owner=sample_owner,
        ),
        PerformanceRule(
            thresholds=grouped_thresholds["performance"] or list(resolved_policy.thresholds.values()),
            threshold_failures=threshold_failures,
            top_k=resolved_policy.top_k,
            topk_selected=topk_selected,
            topk_ranks=topk_ranks,
            on_missing_metric=validation_cfg.on_missing_metric,
            severity=performance_severity,
            owner=performance_owner,
        ),
        RiskConstraintRule(
            correlation_rule=resolved_policy.correlation,
            hysteresis_rule=resolved_policy.hysteresis,
            correlation_violations=correlation_violations,
            hysteresis_blocked=hysteresis_blocked,
            severity=risk_severity,
            owner=risk_owner,
        ),
        RobustnessRule(
            dsr_min=robustness_dsr_min,
            cv_sharpe_gap_max=robustness_cv_sharpe_gap_max,
            severity=robustness_severity,
            owner=robustness_owner,
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
            try:
                per_rule[rule.name] = rule.evaluate(strategy_metrics, context)
            except Exception as exc:  # pragma: no cover - defensive fail-closed
                status = "fail" if validation_cfg.on_error == "fail" else "warn"
                tags = getattr(rule, "tags", (rule.name,))
                per_rule[rule.name] = RuleResult(
                    status=status,
                    severity=getattr(rule, "severity", "blocking"),
                    owner=getattr(rule, "owner", "quant"),
                    reason_code="rule_error",
                    reason=str(exc),
                    tags=list(tags),
                    details={"error": repr(exc)},
                )
        rule_results[strategy_id] = per_rule

    cohort_results = evaluate_cohort_rules(normalized, policy, stage=stage)
    portfolio_results = evaluate_portfolio_rules(normalized, policy, stage=stage)
    stress_results = evaluate_stress_rules(normalized, policy, stage=stage)
    live_result = evaluate_live_monitoring(normalized, policy, stage=stage)

    for sid in normalized.keys():
        per_rule = rule_results.setdefault(sid, {})
        if sid in cohort_results:
            per_rule["cohort"] = cohort_results[sid]
        if sid in portfolio_results:
            per_rule["portfolio"] = portfolio_results[sid]
        if sid in stress_results:
            per_rule["stress"] = stress_results[sid]
        if live_result:
            per_rule["live_monitoring"] = live_result

    return PolicyEvaluationResult(
        selected_ids=selected_ids,
        rule_results=rule_results,
        profile=selected_profile,
        ruleset_hash=_ruleset_hash(resolved_policy, profile=selected_profile),
        policy_version=str(policy_version) if policy_version is not None else None,
        recommended_stage=recommended_stage(selected_profile, stage),
    )


def evaluate_extended_layers(
    evaluation_runs: Iterable[Mapping[str, Any]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> Dict[str, Dict[str, RuleResult]]:
    """Evaluate cohort/portfolio/stress/live monitoring layers over EvaluationRun-like payloads.

    Returns:
        Mapping of strategy_id -> rule_name -> RuleResult for the additional layers.
    """
    metrics_map: Dict[str, Dict[str, float]] = {}
    for run in evaluation_runs:
        sid = run.get("strategy_id")
        if not sid:
            continue
        raw_metrics = run.get("metrics")
        if isinstance(raw_metrics, Mapping):
            metrics_map[str(sid)] = _flatten_evaluation_metrics(raw_metrics)

    cohort_results = evaluate_cohort_rules(metrics_map, policy, stage=stage)
    portfolio_results = evaluate_portfolio_rules(metrics_map, policy, stage=stage)
    stress_results = evaluate_stress_rules(metrics_map, policy, stage=stage)
    live_result = evaluate_live_monitoring(metrics_map, policy, stage=stage)

    merged: Dict[str, Dict[str, RuleResult]] = {}
    for sid in metrics_map.keys():
        per_rule: Dict[str, RuleResult] = {}
        if sid in cohort_results:
            per_rule["cohort"] = cohort_results[sid]
        if sid in portfolio_results:
            per_rule["portfolio"] = portfolio_results[sid]
        if sid in stress_results:
            per_rule["stress"] = stress_results[sid]
        if live_result:
            per_rule["live_monitoring"] = live_result
        if per_rule:
            merged[sid] = per_rule
    return merged


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
    *,
    missing_mode: str = "fail",
) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]]]:
    """Evaluate threshold rules with awareness of missing-metric policy.

    missing_mode: fail | warn | ignore
    """
    passed: List[str] = []
    failures: Dict[str, List[Dict[str, Any]]] = {}
    missing_mode_normalized = (missing_mode or "fail").lower()

    for sid, values in metrics.items():
        strategy_failures: List[Dict[str, Any]] = []
        blocking_failure = False
        for rule in thresholds.values():
            val = values.get(rule.metric)
            if val is None:
                if missing_mode_normalized != "ignore":
                    entry = {
                        "metric": rule.metric,
                        "reason": "missing_metric",
                        "mode": missing_mode_normalized,
                        "blocking": missing_mode_normalized == "fail",
                    }
                    strategy_failures.append(entry)
                    if entry["blocking"]:
                        blocking_failure = True
                continue
            if rule.min is not None and val < rule.min:
                strategy_failures.append(
                    {
                        "metric": rule.metric,
                        "reason": "below_min",
                        "min": rule.min,
                        "value": val,
                        "blocking": True,
                    }
                )
                blocking_failure = True
            if rule.max is not None and val > rule.max:
                strategy_failures.append(
                    {
                        "metric": rule.metric,
                        "reason": "above_max",
                        "max": rule.max,
                        "value": val,
                        "blocking": True,
                    }
                )
                blocking_failure = True
        if strategy_failures:
            failures[sid] = strategy_failures
        if not blocking_failure:
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
    on_missing_metric: str = "fail"
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
        severity = self.severity
        mode = (self.on_missing_metric or "fail").lower()
        if not metrics:
            status = "fail" if mode == "fail" else "warn"
            if mode == "ignore":
                severity = "info"
            reason_code = "metrics_missing"
            reason = "No metrics provided for strategy"
        elif missing:
            if mode == "fail":
                status = "fail"
                reason_code = "missing_metric"
            elif mode == "warn":
                status = "warn"
                reason_code = "missing_metric"
            else:
                status = "warn"
                severity = "info"
                reason_code = "missing_metric_ignored"
            reason = f"Missing metrics: {', '.join(sorted(missing))}"
        details = {
            "missing_metrics": missing,
            "available_metrics": sorted(metrics.keys()),
            "policy_on_missing_metric": mode,
        }
        return RuleResult(
            status=status,
            severity=severity,
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
    on_missing_metric: str = "fail"
    name: str = "performance"
    severity: str = "blocking"
    owner: str = "quant"
    tags: Sequence[str] = ("performance", "thresholds")

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        sid = context.strategy_id
        failures = self.threshold_failures.get(sid, [])
        blocking_failures = [f for f in failures if f.get("blocking", True)]
        if blocking_failures:
            reason = self._format_failure_reason(blocking_failures[0])
            return RuleResult(
                status="fail",
                severity=self.severity,
                owner=self.owner,
                reason_code="performance_thresholds_failed",
                reason=reason,
                tags=list(self.tags),
                details={"violations": blocking_failures},
            )

        missing_entries = [
            f for f in failures if f.get("reason") == "missing_metric"
        ]
        if missing_entries:
            mode = (self.on_missing_metric or "fail").lower()
            status = "warn" if mode != "fail" else "fail"
            missing_metrics = [item.get("metric") for item in missing_entries]
            reason = f"Missing metrics: {', '.join(missing_metrics)}"
            return RuleResult(
                status=status,
                severity=self.severity,
                owner=self.owner,
                reason_code="performance_metrics_missing",
                reason=reason,
                tags=list(self.tags),
                details={
                    "violations": failures,
                    "policy_on_missing_metric": mode,
                },
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


@dataclass
class RobustnessRule:
    """Validation rule for robustness metrics (§3.1 of validation architecture doc)."""

    dsr_min: float | None = None
    cv_sharpe_gap_max: float | None = None
    name: str = "robustness"
    severity: str = "soft"
    owner: str = "quant"
    tags: Sequence[str] = ("robustness",)

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        dsr = metrics.get("deflated_sharpe_ratio")
        sharpe_first = metrics.get("sharpe_first_half")
        sharpe_second = metrics.get("sharpe_second_half")
        cv_sharpe_mean = metrics.get("cv_sharpe_mean")
        cv_sharpe_std = metrics.get("cv_sharpe_std")

        reasons: list[str] = []
        status = "pass"
        details: Dict[str, Any] = {
            "deflated_sharpe_ratio": dsr,
            "sharpe_first_half": sharpe_first,
            "sharpe_second_half": sharpe_second,
            "cv_sharpe_mean": cv_sharpe_mean,
            "cv_sharpe_std": cv_sharpe_std,
        }

        # Check DSR threshold
        if self.dsr_min is not None:
            if dsr is None:
                status = "warn"
                reasons.append("dsr_missing")
            elif dsr < self.dsr_min:
                status = "fail"
                reasons.append("dsr_below_min")
                details["dsr_min"] = self.dsr_min

        # Check CV sharpe gap (train/test consistency)
        if self.cv_sharpe_gap_max is not None:
            if sharpe_first is not None and sharpe_second is not None:
                gap = abs(sharpe_first - sharpe_second)
                details["sharpe_gap"] = gap
                if gap > self.cv_sharpe_gap_max:
                    status = "fail" if status != "fail" else status
                    reasons.append("cv_sharpe_gap_exceeds_max")
                    details["cv_sharpe_gap_max"] = self.cv_sharpe_gap_max

        reason_code = reasons[0] if reasons else "robustness_ok"
        reason = ", ".join(reasons) if reasons else "Robustness checks passed"

        return RuleResult(
            status=status,
            severity=self.severity,
            owner=self.owner,
            reason_code=reason_code,
            reason=reason,
            tags=list(self.tags),
            details=details,
        )


__all__ = [
    "Policy",
    "PolicyEvaluationResult",
    "SelectionConfig",
    "ValidationProfile",
    "CohortRuleConfig",
    "PortfolioRuleConfig",
    "StressRuleConfig",
    "LiveMonitoringConfig",
    "ValidationConfig",
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
    "RobustnessRule",
    "parse_policy",
    "evaluate_policy",
    "recommended_stage",
    "evaluate_cohort_rules",
    "evaluate_portfolio_rules",
    "evaluate_stress_rules",
    "evaluate_live_monitoring",
    "evaluate_extended_layers",
]
