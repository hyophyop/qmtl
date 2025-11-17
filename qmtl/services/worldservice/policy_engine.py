from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import math
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field


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


class Policy(BaseModel):
    thresholds: dict[str, ThresholdRule] = Field(default_factory=dict)
    top_k: TopKRule | None = None
    correlation: CorrelationRule | None = None
    hysteresis: HysteresisRule | None = None


def parse_policy(raw: str | bytes | dict) -> Policy:
    """Parse a policy from YAML/JSON string or pre-parsed dict."""
    data: dict
    if isinstance(raw, (str, bytes)):
        data = yaml.safe_load(raw)
    else:
        data = raw
    return Policy.model_validate(data)


def _apply_thresholds(metrics: Dict[str, Dict[str, float]], policy: Policy) -> List[str]:
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
    metrics: Dict[str, Dict[str, float]],
    policy: Policy,
    prev_active: Iterable[str] | None = None,
    correlations: Dict[Tuple[str, str], float] | None = None,
) -> List[str]:
    """Return strategy ids that satisfy the policy.

    Args:
        metrics: per-strategy metric mapping.
        policy: policy definition.
        prev_active: previously active strategies for hysteresis.
        correlations: optional pairwise correlation matrix keyed by tuple(sorted((a,b))).
    """
    candidates = _apply_thresholds(metrics, policy)
    if policy.top_k:
        candidates = _apply_topk(metrics, candidates, policy.top_k)
    if policy.correlation:
        candidates = _apply_correlation(correlations, candidates, policy.correlation)
    if policy.hysteresis:
        candidates = _apply_hysteresis(metrics, candidates, prev_active, policy.hysteresis)
    return list(candidates)


__all__ = [
    "Policy",
    "ThresholdRule",
    "TopKRule",
    "CorrelationRule",
    "HysteresisRule",
    "parse_policy",
    "evaluate_policy",
]
