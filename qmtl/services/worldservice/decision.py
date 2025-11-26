"""Decision evaluation helpers for world service flows."""

from __future__ import annotations

from typing import Dict, List

from fastapi import HTTPException

from qmtl.runtime.transforms.linearity_metrics import (
    equity_linearity_metrics,
    equity_linearity_metrics_v2,
)

from .policy_engine import evaluate_policy
from .schemas import ApplyRequest, EvaluateRequest, StrategySeries
from .alpha_metrics import (
    alpha_performance_metrics_from_returns,
    alpha_performance_metrics_from_series,
    equity_curve_to_returns,
)
from .storage import Storage


def augment_metrics_with_linearity(
    metrics: Dict[str, Dict[str, float]],
    series: Dict[str, StrategySeries] | None,
) -> Dict[str, Dict[str, float]]:
    augmentor = _LinearityMetricsAugmentor()
    return augmentor.augment(metrics, series)


def _materialize_equity_curve(series: StrategySeries) -> List[float] | None:
    if series.equity:
        return list(series.equity)
    if series.pnl:
        return list(series.pnl)
    if series.returns:
        cumulative = 0.0
        eq: List[float] = []
        for value in series.returns:
            cumulative += float(value)
            eq.append(cumulative)
        return eq
    return None


class _LinearityMetricsAugmentor:
    """Strategy-style helper to augment metrics with linearity signals."""

    def augment(
        self,
        metrics: Dict[str, Dict[str, float]],
        series: Dict[str, StrategySeries] | None,
    ) -> Dict[str, Dict[str, float]]:
        if not series:
            return metrics

        out: Dict[str, Dict[str, float]] = {k: dict(v) for k, v in (metrics or {}).items()}
        equities = self._extract_equity_series(series, out)
        self._augment_with_portfolio_metrics(equities, out)
        return out

    def _extract_equity_series(
        self,
        series: Dict[str, StrategySeries],
        out: Dict[str, Dict[str, float]],
    ) -> Dict[str, List[float]]:
        equities: Dict[str, List[float]] = {}
        for sid, s in series.items():
            eq = _materialize_equity_curve(s)
            if not eq or len(eq) < 2:
                continue
            equities[sid] = eq
            m1 = equity_linearity_metrics(eq)
            m2 = equity_linearity_metrics_v2(eq)
            slot = out.setdefault(sid, {})
            slot.update(
                {
                    "el_v1_score": m1["score"],
                    "el_v1_r2_up": m1["r2_up"],
                    "el_v1_straightness": m1["straightness_ratio"],
                    "el_v1_monotonicity": m1["monotonicity"],
                    "el_v1_new_high_frac": m1["new_high_frac"],
                    "el_v1_net_gain": m1["net_gain"],
                    "el_v2_score": m2["score"],
                    "el_v2_tvr": m2["tvr"],
                    "el_v2_tuw": m2["tuw"],
                    "el_v2_r2_up": m2["r2_up"],
                    "el_v2_spearman_rho": m2["spearman_rho"],
                    "el_v2_t_slope": m2["t_slope"],
                    "el_v2_t_slope_sig": m2["t_slope_sig"],
                    "el_v2_mdd_norm": m2["mdd_norm"],
                    "el_v2_net_gain": m2["net_gain"],
                }
            )
            slot.update(alpha_performance_metrics_from_series(s))
        return equities

    def _augment_with_portfolio_metrics(
        self,
        equities: Dict[str, List[float]],
        out: Dict[str, Dict[str, float]],
    ) -> None:
        if not equities:
            return
        minlen = min(len(v) for v in equities.values())
        if minlen < 2:
            return
        portfolio = [sum(v[i] for v in equities.values()) for i in range(minlen)]
        p1 = equity_linearity_metrics(portfolio)
        p2 = equity_linearity_metrics_v2(portfolio)
        portfolio_returns = equity_curve_to_returns(portfolio)
        for sid in equities.keys():
            slot = out.setdefault(sid, {})
            slot.update(
                {
                    "portfolio_el_v1_score": p1["score"],
                    "portfolio_el_v2_score": p2["score"],
                    "portfolio_el_v2_tvr": p2["tvr"],
                    "portfolio_el_v2_tuw": p2["tuw"],
                    "portfolio_el_v2_mdd_norm": p2["mdd_norm"],
                }
            )
            slot.update(alpha_performance_metrics_from_returns(portfolio_returns))


class DecisionEvaluator:
    """Augment metric payloads and evaluate gating policies."""

    def __init__(self, store: Storage) -> None:
        self.store = store

    async def determine_active(
        self, world_id: str, payload: ApplyRequest | EvaluateRequest
    ) -> List[str]:
        if isinstance(payload, ApplyRequest) and payload.plan:
            prev = payload.previous or await self.store.get_decisions(world_id)
            activate = set(payload.plan.activate)
            deactivate = set(payload.plan.deactivate)
            return sorted((set(prev) - deactivate) | activate)

        policy_payload = payload.policy or await self.store.get_default_policy(world_id)
        policy = policy_payload
        if not isinstance(policy, Policy):
            try:
                if isinstance(policy_payload, dict) and "policy" in policy_payload:
                    policy = Policy.model_validate(policy_payload["policy"])
                else:
                    policy = Policy.model_validate(policy_payload)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"invalid policy: {exc}") from exc
        if policy is None:
            raise HTTPException(status_code=404, detail="policy not found")
        prev = payload.previous or await self.store.get_decisions(world_id)
        metrics = augment_metrics_with_linearity(
            payload.metrics or {}, getattr(payload, "series", None)
        )
        return evaluate_policy(metrics, policy, prev, payload.correlations)


__all__ = ["DecisionEvaluator", "augment_metrics_with_linearity"]
