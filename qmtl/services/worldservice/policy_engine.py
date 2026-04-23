from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    Protocol,
    Sequence,
    Tuple,
)

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


class BenchmarkRuleConfig(BaseModel):
    """Configuration for benchmark-relative rules (challenger vs benchmark)."""

    min_vs_benchmark_sharpe: float | None = None
    severity: str | None = None
    owner: str | None = None


class StressRuleConfig(BaseModel):
    """Configuration for stress-scenario based validation."""

    scenarios: Dict[str, Dict[str, float]] | None = None
    severity: str | None = None
    owner: str | None = None


class PaperShadowConsistencyConfig(BaseModel):
    """Configuration for paper/shadow vs backtest drift detection."""

    stages: List[str] | None = None  # default: ["paper", "shadow"]
    min_sharpe_ratio: float | None = None
    max_drawdown_ratio: float | None = None
    max_var_p01_ratio: float | None = None
    max_es_p01_ratio: float | None = None
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


class LivePromotionConfig(BaseModel):
    """World-level governance configuration for live promotion execution."""

    mode: Literal["disabled", "manual_approval", "auto_apply"] = "manual_approval"
    cooldown: str | None = None
    max_live_slots: int | None = None
    canary_fraction: float | None = None
    approvers: List[str] | None = None


class GovernanceConfig(BaseModel):
    live_promotion: LivePromotionConfig | None = None


class CampaignStageConfig(BaseModel):
    window: str | None = None


class CampaignCommonConfig(BaseModel):
    min_sample_days: int | None = None
    min_trades_total: int | None = None


class CampaignConfig(BaseModel):
    """World-level campaign observation configuration (Phase 4)."""

    backtest: CampaignStageConfig | None = None
    paper: CampaignStageConfig | None = None
    common: CampaignCommonConfig | None = None


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
    benchmark: BenchmarkRuleConfig | None = None
    stress: StressRuleConfig | None = None
    paper_shadow_consistency: PaperShadowConsistencyConfig | None = None
    live_monitoring: LiveMonitoringConfig | None = None
    governance: GovernanceConfig | None = None
    campaign: CampaignConfig | None = None

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


def _resolve_profile_candidate(
    candidate: str | None,
    normalized_profiles: Mapping[str, str],
) -> str | None:
    normalized = _normalize_key(candidate)
    if normalized and normalized in normalized_profiles:
        return normalized_profiles[normalized]
    return None


def _mapped_profiles_for_stage(policy: Policy, stage: str | None) -> list[str]:
    normalized_stage = _normalize_key(stage)
    if not normalized_stage:
        return []
    mapping = {_normalize_key(k) or "": v for k, v in policy.default_profile_by_stage.items()}
    candidates: list[str] = []
    for key in (normalized_stage, f"{normalized_stage}_only"):
        mapped = mapping.get(key)
        if mapped:
            candidates.append(mapped)
    if stage:
        candidates.append(stage)
    return candidates


def _choose_profile(policy: Policy, stage: str | None, profile: str | None) -> str | None:
    if not policy.validation_profiles:
        return None
    profiles = policy.validation_profiles
    normalized_profiles: Dict[str, str] = {_normalize_key(name) or "": name for name in profiles}

    candidates: list[str | None] = [profile]
    candidates.extend(_mapped_profiles_for_stage(policy, stage))
    candidates.extend(policy.default_profile_by_stage.values())
    for candidate in candidates:
        selected = _resolve_profile_candidate(candidate, normalized_profiles)
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


def _as_number(value: Any, *, absolute: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return abs(numeric) if absolute else numeric


def _evaluate_optional_upper_bound(
    *,
    value: float | None,
    threshold: float | None,
    missing_reason: str,
    fail_reason: str,
    detail_key: str,
    details: Dict[str, Any],
) -> tuple[Literal["warn", "fail"], str] | None:
    if threshold is None:
        return None
    details[detail_key] = threshold
    if value is None:
        return "warn", missing_reason
    if value > threshold:
        return "fail", fail_reason
    return None


def _evaluate_optional_lower_bound(
    *,
    value: float | None,
    threshold: float | None,
    missing_reason: str,
    fail_reason: str,
    detail_key: str,
    details: Dict[str, Any],
) -> tuple[Literal["warn", "fail"], str] | None:
    if threshold is None:
        return None
    details[detail_key] = threshold
    if value is None:
        return "warn", missing_reason
    if value < threshold:
        return "fail", fail_reason
    return None


def _apply_rule_event(
    status: str,
    reasons: list[str],
    event: tuple[Literal["warn", "fail"], str] | None,
) -> str:
    if event is None:
        return status
    level, reason = event
    reasons.append(reason)
    if level == "fail":
        return "fail"
    if status == "pass":
        return "warn"
    return status


def _primary_reason(fail_reasons: list[str], warn_reasons: list[str], default_reason: str) -> str:
    if fail_reasons:
        return fail_reasons[0]
    if warn_reasons:
        return warn_reasons[0]
    return default_reason


def _metric_series(metrics: Mapping[str, Mapping[str, Any]], key: str) -> list[float]:
    series: list[float] = []
    for values in metrics.values():
        number = _as_number(values.get(key))
        if number is not None:
            series.append(number)
    return series


def _cohort_topk_selected(
    metrics: Mapping[str, Mapping[str, Any]],
    top_k: int | None,
    sharpe_values: Sequence[float],
) -> set[str]:
    if not top_k or not sharpe_values:
        return set()
    ranked = sorted(metrics.items(), key=lambda item: item[1].get("sharpe", float("-inf")), reverse=True)
    return {sid for sid, _ in ranked[:top_k]}


def _evaluate_cohort_strategy(
    sid: str,
    vals: Mapping[str, Any],
    *,
    cfg: CohortRuleConfig,
    median_sharpe: float | None,
    median_dsr: float | None,
    topk_selected: set[str],
    severity: str,
    owner: str,
) -> RuleResult:
    reasons: list[str] = []
    status = "pass"
    details: Dict[str, Any] = {
        "median_sharpe": median_sharpe,
        "median_dsr": median_dsr,
        "top_k": cfg.top_k,
        "selected_in_top_k": sid in topk_selected if topk_selected else None,
        "sharpe": vals.get("sharpe"),
        "deflated_sharpe_ratio": vals.get("deflated_sharpe_ratio"),
    }
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_lower_bound(
            value=median_sharpe,
            threshold=cfg.sharpe_median_min,
            missing_reason="median_sharpe_missing",
            fail_reason="cohort_median_sharpe_below_min",
            detail_key="sharpe_median_min",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_lower_bound(
            value=median_dsr,
            threshold=cfg.dsr_median_min,
            missing_reason="median_dsr_missing",
            fail_reason="cohort_median_dsr_below_min",
            detail_key="dsr_median_min",
            details=details,
        ),
    )

    if cfg.top_k:
        topk_event = ("warn", "top_k_unavailable") if not topk_selected else None
        if topk_selected and sid not in topk_selected:
            topk_event = ("fail", "cohort_top_k_exceeded")
        status = _apply_rule_event(status, reasons, topk_event)

    reason_code = reasons[0] if reasons else "cohort_ok"
    reason = ", ".join(reasons) if reasons else "Cohort criteria satisfied"
    return RuleResult(
        status=status,
        severity=severity,
        owner=owner,
        reason_code=reason_code,
        reason=reason,
        tags=["cohort"],
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
    sharpe_values = _metric_series(metrics, "sharpe")
    dsr_values = _metric_series(metrics, "deflated_sharpe_ratio")
    median_sharpe = statistics.median(sharpe_values) if sharpe_values else None
    median_dsr = statistics.median(dsr_values) if dsr_values else None
    topk_selected = _cohort_topk_selected(metrics, cfg.top_k, sharpe_values)

    return {
        sid: _evaluate_cohort_strategy(
            sid,
            vals,
            cfg=cfg,
            median_sharpe=median_sharpe,
            median_dsr=median_dsr,
            topk_selected=topk_selected,
            severity=severity,
            owner=owner,
        )
        for sid, vals in metrics.items()
    }


def _evaluate_portfolio_strategy(
    vals: Mapping[str, Any],
    *,
    cfg: PortfolioRuleConfig,
    severity: str,
    owner: str,
) -> RuleResult:
    reasons: list[str] = []
    status = "pass"
    details: Dict[str, Any] = {
        "max_incremental_var_99": vals.get("incremental_var_99"),
        "max_incremental_es_99": vals.get("incremental_es_99"),
        "portfolio_sharpe_uplift": vals.get("portfolio_sharpe_uplift"),
    }
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_upper_bound(
            value=_as_number(vals.get("incremental_var_99")),
            threshold=cfg.max_incremental_var_99,
            missing_reason="incremental_var_missing",
            fail_reason="incremental_var_exceeds_max",
            detail_key="incremental_var_99_max",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_upper_bound(
            value=_as_number(vals.get("incremental_es_99")),
            threshold=cfg.max_incremental_es_99,
            missing_reason="incremental_es_missing",
            fail_reason="incremental_es_exceeds_max",
            detail_key="incremental_es_99_max",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_lower_bound(
            value=_as_number(vals.get("portfolio_sharpe_uplift")),
            threshold=cfg.min_portfolio_sharpe_uplift,
            missing_reason="portfolio_sharpe_uplift_missing",
            fail_reason="portfolio_sharpe_uplift_below_min",
            detail_key="min_portfolio_sharpe_uplift",
            details=details,
        ),
    )

    reason_code = reasons[0] if reasons else "portfolio_ok"
    reason = ", ".join(reasons) if reasons else "Portfolio constraints satisfied"
    return RuleResult(
        status=status,
        severity=severity,
        owner=owner,
        reason_code=reason_code,
        reason=reason,
        tags=["portfolio"],
        details=details,
    )


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
    return {sid: _evaluate_portfolio_strategy(vals, cfg=cfg, severity=severity, owner=owner) for sid, vals in metrics.items()}


def evaluate_benchmark_rules(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> Dict[str, RuleResult]:
    """Evaluate benchmark-relative rules if benchmark comparison metrics are present."""

    cfg = policy.benchmark
    if cfg is None:
        return {}
    severity, owner = _resolve_meta_defaults(cfg, default_severity="soft", default_owner="quant")
    results: Dict[str, RuleResult] = {}

    for sid, vals in metrics.items():
        status = "pass"
        reasons: list[str] = []
        uplift = vals.get("vs_benchmark_sharpe")
        details: Dict[str, Any] = {
            "stage": stage,
            "sharpe": vals.get("sharpe"),
            "benchmark_sharpe": vals.get("benchmark_sharpe"),
            "vs_benchmark_sharpe": uplift,
        }

        if cfg.min_vs_benchmark_sharpe is not None:
            if uplift is None:
                status = "warn"
                reasons.append("benchmark_uplift_missing")
            elif uplift < cfg.min_vs_benchmark_sharpe:
                status = "fail"
                reasons.append("benchmark_uplift_below_min")
                details["min_vs_benchmark_sharpe"] = cfg.min_vs_benchmark_sharpe

        reason_code = reasons[0] if reasons else "benchmark_ok"
        reason = ", ".join(reasons) if reasons else "Benchmark comparison satisfied"
        results[sid] = RuleResult(
            status=status,
            severity=severity,
            owner=owner,
            reason_code=reason_code,
            reason=reason,
            tags=["benchmark"],
            details=details,
        )

    return results


def _stress_metric_value(
    vals: Mapping[str, Any],
    *,
    metric_prefix: str,
    primary_key: str,
    fallback_key: str | None = None,
) -> float | None:
    raw_value = vals.get(f"{metric_prefix}{primary_key}")
    if raw_value is None and fallback_key:
        raw_value = vals.get(f"{metric_prefix}{fallback_key}")
    return _as_number(raw_value, absolute=True)


def _evaluate_stress_scenario(
    name: str,
    thresholds: Mapping[str, Any],
    vals: Mapping[str, Any],
    details: Dict[str, Any],
) -> tuple[list[str], list[str]]:
    fail_reasons: list[str] = []
    warn_reasons: list[str] = []
    metric_prefix = f"stress.{name}."
    dd_value = _stress_metric_value(vals, metric_prefix=metric_prefix, primary_key="max_drawdown", fallback_key="dd_max")
    es_value = _stress_metric_value(vals, metric_prefix=metric_prefix, primary_key="es_99")
    var_value = _stress_metric_value(vals, metric_prefix=metric_prefix, primary_key="var_99")

    checks = [
        _evaluate_optional_upper_bound(
            value=dd_value,
            threshold=thresholds.get("dd_max"),
            missing_reason=f"{name}_dd_missing",
            fail_reason=f"{name}_dd_exceeds_max",
            detail_key=f"{name}_dd_max",
            details=details,
        ),
        _evaluate_optional_upper_bound(
            value=es_value,
            threshold=thresholds.get("es_99"),
            missing_reason=f"{name}_es_missing",
            fail_reason=f"{name}_es_exceeds_max",
            detail_key=f"{name}_es_99_max",
            details=details,
        ),
        _evaluate_optional_upper_bound(
            value=var_value,
            threshold=thresholds.get("var_99"),
            missing_reason=f"{name}_var_missing",
            fail_reason=f"{name}_var_exceeds_max",
            detail_key=f"{name}_var_99_max",
            details=details,
        ),
    ]
    for event in checks:
        if event is None:
            continue
        if event[0] == "fail":
            fail_reasons.append(event[1])
        else:
            warn_reasons.append(event[1])
    return fail_reasons, warn_reasons


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
        fail_reasons: list[str] = []
        warn_reasons: list[str] = []
        details: Dict[str, Any] = {"scenarios": list(scenarios.keys()), "stage": stage}

        for name, thresholds in scenarios.items():
            scenario_failures, scenario_warnings = _evaluate_stress_scenario(name, thresholds, vals, details)
            fail_reasons.extend(scenario_failures)
            warn_reasons.extend(scenario_warnings)

        status = "fail" if fail_reasons else "warn" if warn_reasons else "pass"
        reason_code = _primary_reason(fail_reasons, warn_reasons, "stress_ok")
        combined = fail_reasons + warn_reasons
        reason = ", ".join(combined) if combined else "Stress scenarios satisfied"
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


def _paper_shadow_allowed_for_stage(cfg: PaperShadowConsistencyConfig, stage: str | None) -> bool:
    stage_norm = _normalize_key(stage) or ""
    allowed_raw = cfg.stages or ["paper", "shadow"]
    allowed = {_normalize_key(s) or "" for s in allowed_raw}
    return not stage_norm or stage_norm in allowed


def _paper_shadow_details(vals: Mapping[str, Any], stage: str | None) -> Dict[str, Any]:
    sharpe_ratio = vals.get("paper_vs_backtest_sharpe_ratio")
    dd_ratio = vals.get("paper_vs_backtest_dd_ratio")
    var_ratio = vals.get("paper_vs_backtest_var_p01_ratio")
    es_ratio = vals.get("paper_vs_backtest_es_p01_ratio")
    return {
        "stage": stage,
        "baseline_run_id": vals.get("paper_shadow_baseline_run_id"),
        "backtest_sharpe": vals.get("backtest_sharpe"),
        "backtest_max_drawdown": vals.get("backtest_max_drawdown"),
        "backtest_var_p01": vals.get("backtest_var_p01"),
        "backtest_es_p01": vals.get("backtest_es_p01"),
        "paper_sharpe": vals.get("sharpe"),
        "paper_max_drawdown": vals.get("max_drawdown"),
        "paper_var_p01": vals.get("var_p01") or vals.get("returns.var_p01"),
        "paper_es_p01": vals.get("es_p01") or vals.get("returns.es_p01"),
        "paper_vs_backtest_sharpe_ratio": sharpe_ratio,
        "paper_vs_backtest_dd_ratio": dd_ratio,
        "paper_vs_backtest_var_p01_ratio": var_ratio,
        "paper_vs_backtest_es_p01_ratio": es_ratio,
    }


def _evaluate_paper_shadow_strategy(
    vals: Mapping[str, Any],
    *,
    cfg: PaperShadowConsistencyConfig,
    stage: str | None,
    severity: str,
    owner: str,
) -> RuleResult:
    status = "pass"
    reasons: list[str] = []
    details = _paper_shadow_details(vals, stage)
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_lower_bound(
            value=_as_number(details["paper_vs_backtest_sharpe_ratio"]),
            threshold=cfg.min_sharpe_ratio,
            missing_reason="paper_shadow_sharpe_ratio_missing",
            fail_reason="paper_shadow_sharpe_ratio_below_min",
            detail_key="min_sharpe_ratio",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_upper_bound(
            value=_as_number(details["paper_vs_backtest_dd_ratio"]),
            threshold=cfg.max_drawdown_ratio,
            missing_reason="paper_shadow_dd_ratio_missing",
            fail_reason="paper_shadow_dd_ratio_exceeds_max",
            detail_key="max_drawdown_ratio",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_upper_bound(
            value=_as_number(details["paper_vs_backtest_var_p01_ratio"]),
            threshold=cfg.max_var_p01_ratio,
            missing_reason="paper_shadow_var_ratio_missing",
            fail_reason="paper_shadow_var_ratio_exceeds_max",
            detail_key="max_var_p01_ratio",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_upper_bound(
            value=_as_number(details["paper_vs_backtest_es_p01_ratio"]),
            threshold=cfg.max_es_p01_ratio,
            missing_reason="paper_shadow_es_ratio_missing",
            fail_reason="paper_shadow_es_ratio_exceeds_max",
            detail_key="max_es_p01_ratio",
            details=details,
        ),
    )

    reason_code = reasons[0] if reasons else "paper_shadow_ok"
    reason = ", ".join(reasons) if reasons else "Paper/shadow consistency satisfied"
    return RuleResult(
        status=status,
        severity=severity,
        owner=owner,
        reason_code=reason_code,
        reason=reason,
        tags=["paper_shadow"],
        details=details,
    )


def evaluate_paper_shadow_consistency(
    metrics: Mapping[str, Mapping[str, Any]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> Dict[str, RuleResult]:
    """Evaluate paper/shadow consistency against stored backtest baselines."""

    cfg = policy.paper_shadow_consistency
    if cfg is None:
        return {}
    if not _paper_shadow_allowed_for_stage(cfg, stage):
        return {}

    severity, owner = _resolve_meta_defaults(cfg, default_severity="soft", default_owner="ops")
    return {
        sid: _evaluate_paper_shadow_strategy(
            vals,
            cfg=cfg,
            stage=stage,
            severity=severity,
            owner=owner,
        )
        for sid, vals in metrics.items()
    }


def _live_metric_values(
    metrics: Mapping[str, Mapping[str, Any]],
    primary_key: str,
    fallback_key: str | None = None,
) -> list[float]:
    values: list[float] = []
    for strategy_metrics in metrics.values():
        raw_value = strategy_metrics.get(primary_key)
        if raw_value is None and fallback_key:
            raw_value = strategy_metrics.get(fallback_key)
        numeric = _as_number(raw_value)
        if numeric is not None:
            values.append(numeric)
    return values


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

    sharpe_values = _live_metric_values(metrics, "live_sharpe", "realized_sharpe")
    dd_values = _live_metric_values(metrics, "live_max_drawdown", "realized_max_drawdown")
    decay_values = _live_metric_values(metrics, "live_vs_backtest_sharpe_ratio")

    reasons: list[str] = []
    status = "pass"
    details: Dict[str, Any] = {
        "sharpe_mean": statistics.mean(sharpe_values) if sharpe_values else None,
        "dd_mean": statistics.mean(dd_values) if dd_values else None,
        "decay_mean": statistics.mean(decay_values) if decay_values else None,
        "lookback_days": lookback,
    }

    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_lower_bound(
            value=details["sharpe_mean"],
            threshold=sharpe_min,
            missing_reason="live_sharpe_missing",
            fail_reason="live_sharpe_below_min",
            detail_key="sharpe_min",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_upper_bound(
            value=details["dd_mean"],
            threshold=dd_max,
            missing_reason="live_dd_missing",
            fail_reason="live_dd_exceeds_max",
            detail_key="dd_max",
            details=details,
        ),
    )
    status = _apply_rule_event(
        status,
        reasons,
        _evaluate_optional_lower_bound(
            value=details["decay_mean"],
            threshold=decay_threshold,
            missing_reason="live_decay_missing",
            fail_reason="live_decay_below_threshold",
            detail_key="decay_threshold",
            details=details,
        ),
    )

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


@dataclass
class _PolicySelectionPreparation:
    selected_ids: List[str]
    threshold_failures: Dict[str, List[Dict[str, Any]]]
    topk_selected: set[str]
    topk_ranks: Dict[str, int]
    correlation_violations: Dict[str, List[Tuple[str, float]]]
    hysteresis_blocked: Dict[str, str]


@dataclass
class _RuleAssemblyProfileConfig:
    sample_severity: str
    sample_owner: str
    performance_severity: str
    performance_owner: str
    risk_severity: str
    risk_owner: str
    robustness_severity: str
    robustness_owner: str
    robustness_dsr_min: float | None
    robustness_cv_sharpe_gap_max: float | None


@dataclass
class _CrossStrategyLayerEvaluation:
    cohort_results: Dict[str, RuleResult]
    portfolio_results: Dict[str, RuleResult]
    benchmark_results: Dict[str, RuleResult]
    stress_results: Dict[str, RuleResult]
    paper_shadow_results: Dict[str, RuleResult]
    live_result: RuleResult | None


def _prepare_policy_selection(
    normalized: Dict[str, Dict[str, float]],
    resolved_policy: Policy,
    validation_cfg: ValidationConfig,
    prev_active: Iterable[str] | None,
    correlations: Dict[Tuple[str, str], float] | None,
) -> _PolicySelectionPreparation:
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

    return _PolicySelectionPreparation(
        selected_ids=list(candidates),
        threshold_failures=threshold_failures,
        topk_selected=topk_selected,
        topk_ranks=topk_ranks,
        correlation_violations=correlation_violations,
        hysteresis_blocked=hysteresis_blocked,
    )


def _profile_attr(section: Any, attr: str, default: Any) -> Any:
    if section is None:
        return default
    value = getattr(section, attr, None)
    return default if value is None else value


def _resolve_rule_assembly_profile_config(
    selected_profile_cfg: ValidationProfile | None,
) -> _RuleAssemblyProfileConfig:
    sample_cfg = selected_profile_cfg.sample if selected_profile_cfg else None
    performance_cfg = selected_profile_cfg.performance if selected_profile_cfg else None
    risk_cfg = selected_profile_cfg.risk if selected_profile_cfg else None
    robustness_cfg = selected_profile_cfg.robustness if selected_profile_cfg else None
    return _RuleAssemblyProfileConfig(
        sample_severity=_profile_attr(sample_cfg, "severity", "soft"),
        sample_owner=_profile_attr(sample_cfg, "owner", "quant"),
        performance_severity=_profile_attr(performance_cfg, "severity", "blocking"),
        performance_owner=_profile_attr(performance_cfg, "owner", "quant"),
        risk_severity=_profile_attr(risk_cfg, "severity", "blocking"),
        risk_owner=_profile_attr(risk_cfg, "owner", "risk"),
        robustness_severity=_profile_attr(robustness_cfg, "severity", "soft"),
        robustness_owner=_profile_attr(robustness_cfg, "owner", "quant"),
        robustness_dsr_min=_profile_attr(robustness_cfg, "dsr_min", None),
        robustness_cv_sharpe_gap_max=_profile_attr(robustness_cfg, "cv_sharpe_gap_max", None),
    )


def _assemble_policy_rules(
    resolved_policy: Policy,
    validation_cfg: ValidationConfig,
    selection: _PolicySelectionPreparation,
    selected_profile_cfg: ValidationProfile | None,
) -> List[ValidationRule]:
    grouped_thresholds = _group_thresholds(resolved_policy.thresholds)
    profile_cfg = _resolve_rule_assembly_profile_config(selected_profile_cfg)
    return [
        DataCurrencyRule(
            required_metrics=[t.metric for t in grouped_thresholds["data_currency"]],
            on_missing_metric=validation_cfg.on_missing_metric,
        ),
        SampleRule(
            thresholds=grouped_thresholds["sample"],
            severity=profile_cfg.sample_severity,
            owner=profile_cfg.sample_owner,
        ),
        PerformanceRule(
            thresholds=grouped_thresholds["performance"] or list(resolved_policy.thresholds.values()),
            threshold_failures=selection.threshold_failures,
            top_k=resolved_policy.top_k,
            topk_selected=selection.topk_selected,
            topk_ranks=selection.topk_ranks,
            on_missing_metric=validation_cfg.on_missing_metric,
            severity=profile_cfg.performance_severity,
            owner=profile_cfg.performance_owner,
        ),
        RiskConstraintRule(
            correlation_rule=resolved_policy.correlation,
            hysteresis_rule=resolved_policy.hysteresis,
            correlation_violations=selection.correlation_violations,
            hysteresis_blocked=selection.hysteresis_blocked,
            severity=profile_cfg.risk_severity,
            owner=profile_cfg.risk_owner,
        ),
        RobustnessRule(
            dsr_min=profile_cfg.robustness_dsr_min,
            cv_sharpe_gap_max=profile_cfg.robustness_cv_sharpe_gap_max,
            severity=profile_cfg.robustness_severity,
            owner=profile_cfg.robustness_owner,
        ),
    ]


def _evaluate_rule_results(
    normalized: Dict[str, Dict[str, float]],
    rules: Sequence[ValidationRule],
    validation_cfg: ValidationConfig,
    prev_active: Iterable[str] | None,
    correlations: Dict[Tuple[str, str], float] | None,
) -> Dict[str, Dict[str, RuleResult]]:
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
    return rule_results


def _evaluate_cross_strategy_layers(
    metrics: Mapping[str, Mapping[str, float]],
    policy: Policy,
    *,
    stage: str | None = None,
) -> _CrossStrategyLayerEvaluation:
    return _CrossStrategyLayerEvaluation(
        cohort_results=evaluate_cohort_rules(metrics, policy, stage=stage),
        portfolio_results=evaluate_portfolio_rules(metrics, policy, stage=stage),
        benchmark_results=evaluate_benchmark_rules(metrics, policy, stage=stage),
        stress_results=evaluate_stress_rules(metrics, policy, stage=stage),
        paper_shadow_results=evaluate_paper_shadow_consistency(metrics, policy, stage=stage),
        live_result=evaluate_live_monitoring(metrics, policy, stage=stage),
    )


def _merge_cross_strategy_layers(
    base_results: Dict[str, Dict[str, RuleResult]],
    strategy_ids: Iterable[str],
    cross_layers: _CrossStrategyLayerEvaluation,
    *,
    include_empty: bool = False,
) -> Dict[str, Dict[str, RuleResult]]:
    merged = base_results
    for sid in strategy_ids:
        per_rule = merged.setdefault(sid, {})
        if sid in cross_layers.cohort_results:
            per_rule["cohort"] = cross_layers.cohort_results[sid]
        if sid in cross_layers.portfolio_results:
            per_rule["portfolio"] = cross_layers.portfolio_results[sid]
        if sid in cross_layers.benchmark_results:
            per_rule["benchmark"] = cross_layers.benchmark_results[sid]
        if sid in cross_layers.stress_results:
            per_rule["stress"] = cross_layers.stress_results[sid]
        if sid in cross_layers.paper_shadow_results:
            per_rule["paper_shadow_consistency"] = cross_layers.paper_shadow_results[sid]
        if cross_layers.live_result:
            per_rule["live_monitoring"] = cross_layers.live_result
        if not per_rule and not include_empty:
            merged.pop(sid, None)
    return merged


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
    selection = _prepare_policy_selection(
        normalized=normalized,
        resolved_policy=resolved_policy,
        validation_cfg=validation_cfg,
        prev_active=prev_active,
        correlations=correlations,
    )
    rules = _assemble_policy_rules(
        resolved_policy=resolved_policy,
        validation_cfg=validation_cfg,
        selection=selection,
        selected_profile_cfg=selected_profile_cfg,
    )
    rule_results = _evaluate_rule_results(
        normalized=normalized,
        rules=rules,
        validation_cfg=validation_cfg,
        prev_active=prev_active,
        correlations=correlations,
    )
    cross_layers = _evaluate_cross_strategy_layers(normalized, policy, stage=stage)
    rule_results = _merge_cross_strategy_layers(
        base_results=rule_results,
        strategy_ids=normalized.keys(),
        cross_layers=cross_layers,
        include_empty=True,
    )

    return PolicyEvaluationResult(
        selected_ids=selection.selected_ids,
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

    cross_layers = _evaluate_cross_strategy_layers(metrics_map, policy, stage=stage)
    return _merge_cross_strategy_layers(
        base_results={},
        strategy_ids=metrics_map.keys(),
        cross_layers=cross_layers,
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
                entry = _missing_metric_failure(rule.metric, missing_mode_normalized)
                if entry:
                    strategy_failures.append(entry)
                    blocking_failure = blocking_failure or bool(entry.get("blocking"))
                continue
            violations = _threshold_value_violations(rule, val)
            if violations:
                strategy_failures.extend(violations)
                blocking_failure = True
        if strategy_failures:
            failures[sid] = strategy_failures
        if not blocking_failure:
            passed.append(sid)
    return passed, failures


def _missing_metric_failure(metric: str, mode: str) -> Dict[str, Any] | None:
    if mode == "ignore":
        return None
    return {
        "metric": metric,
        "reason": "missing_metric",
        "mode": mode,
        "blocking": mode == "fail",
    }


def _threshold_value_violations(rule: ThresholdRule, value: float) -> list[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    if rule.min is not None and value < rule.min:
        violations.append(
            {
                "metric": rule.metric,
                "reason": "below_min",
                "min": rule.min,
                "value": value,
                "blocking": True,
            }
        )
    if rule.max is not None and value > rule.max:
        violations.append(
            {
                "metric": rule.metric,
                "reason": "above_max",
                "max": rule.max,
                "value": value,
                "blocking": True,
            }
        )
    return violations


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


def _data_currency_outcome(
    metrics: Mapping[str, float],
    missing: Sequence[str],
    mode: str,
    default_severity: str,
) -> tuple[str, str, str, str]:
    if not metrics:
        severity = "info" if mode == "ignore" else default_severity
        status = "fail" if mode == "fail" else "warn"
        return status, severity, "metrics_missing", "No metrics provided for strategy"
    if missing:
        if mode == "fail":
            return "fail", default_severity, "missing_metric", f"Missing metrics: {', '.join(sorted(missing))}"
        if mode == "warn":
            return "warn", default_severity, "missing_metric", f"Missing metrics: {', '.join(sorted(missing))}"
        return "warn", "info", "missing_metric_ignored", f"Missing metrics: {', '.join(sorted(missing))}"
    return "pass", default_severity, "data_currency_ok", "Required metrics present"


_SAMPLE_METRIC_KEYS = {
    "n_trades_total",
    "n_trades_per_year",
    "num_trades",
    "effective_history_years",
    "sample_days",
}


def _sample_metrics_view(metrics: Mapping[str, float]) -> Dict[str, float]:
    return {key: value for key, value in metrics.items() if key in _SAMPLE_METRIC_KEYS}


def _sample_threshold_failures(
    sample_metrics: Mapping[str, float],
    thresholds: Sequence[ThresholdRule],
) -> list[Dict[str, Any]]:
    if not thresholds:
        return []
    _, failures = _evaluate_thresholds_with_details({"_": sample_metrics}, {t.metric: t for t in thresholds})
    return failures.get("_", [])


def _build_sample_result(
    sample_metrics: Mapping[str, float],
    failures: Sequence[Dict[str, Any]],
    severity: str,
    owner: str,
    tags: Sequence[str],
) -> RuleResult:
    if failures:
        reason = f"Sample thresholds failed: {', '.join(item['metric'] for item in failures)}"
        return RuleResult(
            status="fail",
            severity=severity,
            owner=owner,
            reason_code="sample_thresholds_failed",
            reason=reason,
            tags=list(tags),
            details={"violations": list(failures)},
        )
    has_depth = any(value is not None and value > 0 for value in sample_metrics.values())
    if has_depth:
        return RuleResult(
            status="pass",
            severity=severity,
            owner=owner,
            reason_code="sample_ok",
            reason="Sample depth present",
            tags=list(tags),
            details={"sample_metrics": dict(sample_metrics)},
        )
    return RuleResult(
        status="warn",
        severity=severity,
        owner=owner,
        reason_code="sample_metrics_missing",
        reason="No sample metrics found",
        tags=list(tags),
        details={"sample_metrics": dict(sample_metrics)},
    )


def _performance_failures_for_strategy(
    sid: str,
    threshold_failures: Mapping[str, List[Dict[str, Any]]],
) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    failures = list(threshold_failures.get(sid, []))
    blocking = [failure for failure in failures if failure.get("blocking", True)]
    return failures, blocking


def _performance_missing_result(
    failures: Sequence[Dict[str, Any]],
    on_missing_metric: str,
    *,
    severity: str,
    owner: str,
    tags: Sequence[str],
) -> RuleResult | None:
    missing_entries = [failure for failure in failures if failure.get("reason") == "missing_metric"]
    if not missing_entries:
        return None
    mode = (on_missing_metric or "fail").lower()
    status = "warn" if mode != "fail" else "fail"
    missing_metrics = [item.get("metric") for item in missing_entries]
    reason = f"Missing metrics: {', '.join(missing_metrics)}"
    return RuleResult(
        status=status,
        severity=severity,
        owner=owner,
        reason_code="performance_metrics_missing",
        reason=reason,
        tags=list(tags),
        details={
            "violations": list(failures),
            "policy_on_missing_metric": mode,
        },
    )


def _performance_rank_result(
    sid: str,
    top_k: TopKRule | None,
    topk_selected: set[str],
    topk_ranks: Mapping[str, int],
    *,
    severity: str,
    owner: str,
    tags: Sequence[str],
) -> RuleResult | None:
    if not top_k or sid in topk_selected:
        return None
    rank = topk_ranks.get(sid)
    reason = f"Rank {rank + 1} outside top_k={top_k.k}" if rank is not None else f"Not selected by top_k={top_k.k}"
    return RuleResult(
        status="fail",
        severity=severity,
        owner=owner,
        reason_code="performance_rank_outside_top_k",
        reason=reason,
        tags=list(set(tags) | {"top_k"}),
        details={"rank": rank, "top_k": top_k.k},
    )


def _risk_correlation_failure(
    sid: str,
    rule: CorrelationRule | None,
    violations: Mapping[str, List[Tuple[str, float]]],
    *,
    severity: str,
    owner: str,
    tags: Sequence[str],
) -> RuleResult | None:
    if not rule or sid not in violations:
        return None
    blocked = [{"strategy_id": other, "correlation": corr} for other, corr in violations[sid]]
    return RuleResult(
        status="fail",
        severity=severity,
        owner=owner,
        reason_code="correlation_constraint_failed",
        reason=f"Correlation exceeds max {rule.max}",
        tags=list(tags),
        details={"blocked_by": blocked},
    )


def _risk_hysteresis_failure(
    sid: str,
    metrics: Mapping[str, float],
    context: RuleContext,
    rule: HysteresisRule | None,
    blocked: Mapping[str, str],
    *,
    severity: str,
    owner: str,
    tags: Sequence[str],
) -> RuleResult | None:
    if not rule or sid not in blocked:
        return None
    mode = blocked.get(sid)
    reason_code = "hysteresis_exit" if mode == "exit" else "hysteresis_not_entered"
    reason = (
        f"{rule.metric} below exit {rule.exit} for previously active strategy"
        if mode == "exit"
        else f"{rule.metric} below enter {rule.enter}"
    )
    return RuleResult(
        status="fail",
        severity=severity,
        owner=owner,
        reason_code=reason_code,
        reason=reason,
        tags=list(tags),
        details={
            "metric": rule.metric,
            "previously_active": sid in set(context.previous_active or []),
            "mode": mode,
            "value": metrics.get(rule.metric),
        },
    )


def _robustness_base_details(metrics: Mapping[str, float]) -> Dict[str, Any]:
    return {
        "deflated_sharpe_ratio": metrics.get("deflated_sharpe_ratio"),
        "sharpe_first_half": metrics.get("sharpe_first_half"),
        "sharpe_second_half": metrics.get("sharpe_second_half"),
        "cv_sharpe_mean": metrics.get("cv_sharpe_mean"),
        "cv_sharpe_std": metrics.get("cv_sharpe_std"),
    }


def _robustness_dsr_event(
    dsr: float | None,
    dsr_min: float | None,
    details: Dict[str, Any],
) -> tuple[str, str] | None:
    if dsr_min is None:
        return None
    if dsr is None:
        return "warn", "dsr_missing"
    if dsr < dsr_min:
        details["dsr_min"] = dsr_min
        return "fail", "dsr_below_min"
    return None


def _robustness_gap_event(
    sharpe_first: float | None,
    sharpe_second: float | None,
    max_gap: float | None,
    details: Dict[str, Any],
) -> tuple[str, str] | None:
    if max_gap is None or sharpe_first is None or sharpe_second is None:
        return None
    gap = abs(sharpe_first - sharpe_second)
    details["sharpe_gap"] = gap
    if gap > max_gap:
        details["cv_sharpe_gap_max"] = max_gap
        return "fail", "cv_sharpe_gap_exceeds_max"
    return None


@dataclass
class DataCurrencyRule:
    required_metrics: Sequence[str] | None = None
    on_missing_metric: str = "fail"
    name: str = "data_currency"
    severity: str = "blocking"
    owner: str = "ops"
    tags: Sequence[str] = ("data_currency",)

    def evaluate(self, metrics: Mapping[str, float], context: RuleContext) -> RuleResult:
        required = list(self.required_metrics or [])
        missing = [metric for metric in required if metric not in metrics]
        mode = (self.on_missing_metric or "fail").lower()
        status, severity, reason_code, reason = _data_currency_outcome(
            metrics,
            missing,
            mode,
            self.severity,
        )
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
        sample_metrics = _sample_metrics_view(metrics)
        failures = _sample_threshold_failures(sample_metrics, self.thresholds)
        return _build_sample_result(sample_metrics, failures, self.severity, self.owner, self.tags)


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
        failures, blocking_failures = _performance_failures_for_strategy(sid, self.threshold_failures)
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

        missing_result = _performance_missing_result(
            failures,
            self.on_missing_metric,
            severity=self.severity,
            owner=self.owner,
            tags=self.tags,
        )
        if missing_result:
            return missing_result
        rank_result = _performance_rank_result(
            sid,
            self.top_k,
            self.topk_selected,
            self.topk_ranks,
            severity=self.severity,
            owner=self.owner,
            tags=self.tags,
        )
        if rank_result:
            return rank_result

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
        correlation_result = _risk_correlation_failure(
            sid,
            self.correlation_rule,
            self.correlation_violations,
            severity=self.severity,
            owner=self.owner,
            tags=self.tags,
        )
        if correlation_result:
            return correlation_result
        hysteresis_result = _risk_hysteresis_failure(
            sid,
            metrics,
            context,
            self.hysteresis_rule,
            self.hysteresis_blocked,
            severity=self.severity,
            owner=self.owner,
            tags=self.tags,
        )
        if hysteresis_result:
            return hysteresis_result

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
        reasons: list[str] = []
        status = "pass"
        details = _robustness_base_details(metrics)
        status = _apply_rule_event(
            status,
            reasons,
            _robustness_dsr_event(
                _as_number(details["deflated_sharpe_ratio"]),
                self.dsr_min,
                details,
            ),
        )
        status = _apply_rule_event(
            status,
            reasons,
            _robustness_gap_event(
                _as_number(details["sharpe_first_half"]),
                _as_number(details["sharpe_second_half"]),
                self.cv_sharpe_gap_max,
                details,
            ),
        )

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
    "BenchmarkRuleConfig",
    "StressRuleConfig",
    "PaperShadowConsistencyConfig",
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
    "evaluate_benchmark_rules",
    "evaluate_stress_rules",
    "evaluate_paper_shadow_consistency",
    "evaluate_live_monitoring",
    "evaluate_extended_layers",
]
