"""Helper worker for extended validation layers (cohort/portfolio/stress/live)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import logging
import inspect

from qmtl.services.worldservice.policy_engine import Policy, evaluate_extended_layers

from .storage import Storage
from .validation_metrics import (
    augment_live_metrics,
    augment_portfolio_metrics,
    augment_stress_metrics,
    iso_timestamp_now,
)
from .live_metrics_risk import (
    risk_hub_snapshot_lag_seconds,
    risk_hub_snapshot_missing_total,
)
from .metrics import parse_timestamp

logger = logging.getLogger(__name__)


class ExtendedValidationWorker:
    """Orchestrates evaluation of extended validation layers over stored runs."""

    def __init__(self, store: Storage, risk_hub: Any | None = None) -> None:
        self.store = store
        self.risk_hub = risk_hub

    async def run(
        self,
        world_id: str,
        *,
        stage: str | None = None,
        policy_payload: Any | None = None,
    ) -> int:
        """Evaluate extended layers for a world and persist results."""

        policy = await resolve_policy_for_extended(self.store, world_id, policy_payload)
        if policy is None:
            return 0

        runs = await self.store.list_evaluation_runs(world_id=world_id)
        stage_normalized = (stage or "").lower()
        filtered = [
            run
            for run in runs
            if not stage_normalized
            or str(run.get("stage", "")).lower() == stage_normalized
        ]
        if not filtered:
            return 0

        # Enrich runs with realized/live returns from risk hub snapshots when available.
        hub_payload = await self._latest_hub_snapshot(world_id)
        realized_payload = (
            hub_payload.get("realized_returns") if isinstance(hub_payload, Mapping) else None
        )
        if realized_payload is not None:
            for run in filtered:
                sid = str(run.get("strategy_id") or "")
                if not sid:
                    continue
                metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
                metrics = dict(metrics or {})
                diagnostics = (
                    metrics.get("diagnostics")
                    if isinstance(metrics.get("diagnostics"), Mapping)
                    else {}
                )
                diagnostics = dict(diagnostics or {})
                if diagnostics.get("live_returns") is None:
                    live_returns = self._extract_live_returns(realized_payload, sid)
                    if live_returns:
                        diagnostics["live_returns"] = live_returns
                        metrics["diagnostics"] = diagnostics
                        run["metrics"] = metrics

        stress_payload = (
            hub_payload.get("stress") if isinstance(hub_payload, Mapping) else None
        )
        if stress_payload is not None:
            for run in filtered:
                sid = str(run.get("strategy_id") or "")
                if not sid:
                    continue
                metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
                metrics = dict(metrics or {})
                if metrics.get("stress") is None:
                    stress_for_sid = self._extract_stress_for_strategy(stress_payload, sid)
                    if stress_for_sid:
                        metrics["stress"] = stress_for_sid
                        run["metrics"] = metrics

        # Ensure derived live metrics are present before rule evaluation.
        for run in filtered:
            raw_metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else None
            if raw_metrics is not None:
                derived = augment_live_metrics(raw_metrics)
                derived = augment_stress_metrics(derived, policy_payload=policy_payload)
                run["metrics"] = derived

        extended = evaluate_extended_layers(filtered, policy, stage=stage)
        if not extended:
            return 0

        updated = 0
        for run in filtered:
            strategy_id = run.get("strategy_id")
            if not strategy_id:
                continue
            strategy_id = str(strategy_id)
            if strategy_id not in extended:
                continue

            baseline = await self._portfolio_baseline(world_id, exclude_strategy_id=strategy_id)
            metrics = run.get("metrics") or {}
            if baseline.get("var_99") is not None or baseline.get("es_99") is not None:
                risk_block = metrics.get("risk") if isinstance(metrics, Mapping) else {}
                risk_block = dict(risk_block or {})
                if baseline.get("var_99") is not None:
                    risk_block.setdefault("incremental_var_99", baseline["var_99"])
                if baseline.get("es_99") is not None:
                    risk_block.setdefault("incremental_es_99", baseline["es_99"])
                metrics["risk"] = risk_block
            metrics = augment_live_metrics(metrics)
            metrics = augment_stress_metrics(metrics, policy_payload=policy_payload)
            metrics = augment_portfolio_metrics(
                metrics,
                baseline_sharpe=baseline.get("sharpe"),
                baseline_var_99=baseline.get("var_99"),
                baseline_es_99=baseline.get("es_99"),
            )
            # Ensure baseline-derived increments persist
            if baseline.get("var_99") is not None:
                risk_block = metrics.get("risk") if isinstance(metrics, Mapping) else {}
                risk_block = dict(risk_block or {})
                risk_block.setdefault("incremental_var_99", baseline["var_99"])
                if baseline.get("es_99") is not None:
                    risk_block.setdefault("incremental_es_99", baseline["es_99"])
                metrics["risk"] = risk_block

            validation = dict(run.get("validation") or {})
            history = validation.get("extended_history")
            history_list = list(history) if isinstance(history, list) else []
            results = validation.get("results") if isinstance(validation.get("results"), Mapping) else {}
            merged_results = dict(results)
            for name, result in extended[strategy_id].items():
                merged_results[name] = result.model_dump()
            validation["results"] = merged_results
            prev_revision = validation.get("extended_revision")
            try:
                revision = int(prev_revision) + 1 if prev_revision is not None else 1
            except Exception:
                revision = 1

            evaluated_at = iso_timestamp_now()
            validation["extended_revision"] = revision
            validation["extended_evaluated_at"] = evaluated_at
            history_list.append(
                {
                    "revision": revision,
                    "evaluated_at": evaluated_at,
                    "results": merged_results,
                }
            )
            validation["extended_history"] = history_list

            await self.store.record_evaluation_run(
                world_id,
                strategy_id,
                str(run.get("run_id") or ""),
                stage=str(run.get("stage") or ""),
                risk_tier=str(run.get("risk_tier") or ""),
                model_card_version=run.get("model_card_version"),
                metrics=metrics,
                validation=validation,
                summary=run.get("summary"),
            )

            updated += 1
        return updated

    async def _portfolio_baseline(
        self,
        world_id: str,
        *,
        exclude_strategy_id: str | None = None,
    ) -> dict[str, float | int | None]:
        """Compute a coarse portfolio baseline from latest active strategy runs."""

        hub_snapshot = await self._latest_hub_snapshot(world_id)
        if hub_snapshot:
            weights = hub_snapshot.get("weights") or {}
            cov = hub_snapshot.get("covariance") or {}
            baseline = self._baseline_from_covariance(weights, cov)
            if baseline:
                return baseline

        try:
            active = await self.store.get_decisions(world_id)
        except Exception:
            return {}
        if exclude_strategy_id:
            active = [sid for sid in active if sid != exclude_strategy_id]
        if not active:
            return {}

        weights: dict[str, float] = {}
        try:
            snapshot = await self.store.snapshot_activation(world_id)
            for sid, sides in (snapshot.state or {}).items():
                for entry in sides.values():
                    if entry.get("active"):
                        weights[sid] = weights.get(sid, 0.0) + float(entry.get("weight", 1.0))
        except Exception:
            pass

        runs = await self.store.list_evaluation_runs(world_id=world_id)
        latest: dict[str, Mapping[str, Any]] = {}
        for run in runs:
            sid = str(run.get("strategy_id") or "")
            if sid not in active:
                continue
            ts = parse_timestamp(run.get("updated_at") or run.get("created_at"))
            prev = latest.get(sid)
            prev_ts = parse_timestamp(prev.get("updated_at") or prev.get("created_at")) if prev else None
            if prev is None or (ts and prev_ts and ts > prev_ts) or (ts and not prev_ts):
                latest[sid] = run

        sharpe_sum = 0.0
        weight_sum = 0.0
        var_sum = 0.0
        es_sum = 0.0
        correlations = self._extract_correlations(latest.values())
        z_var_99 = 2.33  # ~99% quantile for N(0,1)

        for sid, run in latest.items():
            metrics = run.get("metrics") if isinstance(run, Mapping) else {}
            returns = metrics.get("returns") if isinstance(metrics, Mapping) else {}
            risk = metrics.get("risk") if isinstance(metrics, Mapping) else {}
            w = weights.get(sid, 1.0)
            sharpe = returns.get("sharpe") if isinstance(returns, Mapping) else None
            if isinstance(sharpe, (int, float)):
                sharpe_sum += float(sharpe) * w
                weight_sum += w

            var_val = None
            if isinstance(risk, Mapping):
                rv = risk.get("incremental_var_99")
                if isinstance(rv, (int, float)):
                    var_val = abs(float(rv))
                ev = risk.get("incremental_es_99")
                if isinstance(ev, (int, float)):
                    es_sum += abs(float(ev)) * w
            if var_val is None and isinstance(returns, Mapping):
                dd = returns.get("max_drawdown")
                if isinstance(dd, (int, float)):
                    var_val = abs(float(dd))
            if var_val is not None:
                var_sum += var_val * w
                if not isinstance(risk, Mapping) or risk.get("incremental_es_99") is None:
                    es_sum += abs(float(var_val)) * w * 1.2

        baseline_sharpe = sharpe_sum / weight_sum if weight_sum else None

        # Covariance-aware aggregate var/es if we have multiple strategies
        portfolio_var = None
        portfolio_es = None
        if latest and weight_sum:
            # Normalize weights to 1.0 for covariance computation
            norm_weights: dict[str, float] = {sid: weights.get(sid, 1.0) / weight_sum for sid in latest.keys()}
            sigmas: dict[str, float] = {}
            for sid, run in latest.items():
                metrics = run.get("metrics") if isinstance(run, Mapping) else {}
                risk_section = metrics.get("risk") if isinstance(metrics, Mapping) else None
                returns = metrics.get("returns") if isinstance(metrics, Mapping) else {}
                var_val = None
                if isinstance(risk_section, Mapping):
                    rv = risk_section.get("incremental_var_99")
                    if isinstance(rv, (int, float)):
                        var_val = abs(float(rv))
                if var_val is None and isinstance(returns, Mapping):
                    dd = returns.get("max_drawdown")
                    if isinstance(dd, (int, float)):
                        var_val = abs(float(dd))
                if var_val is not None and var_val > 0:
                    sigmas[sid] = var_val / z_var_99
            if sigmas:
                variance = 0.0
                sids = list(sigmas.keys())
                for a in sids:
                    for b in sids:
                        rho = 1.0 if a == b else correlations.get((a, b)) or correlations.get((b, a)) or 0.0
                        variance += norm_weights.get(a, 0.0) * norm_weights.get(b, 0.0) * sigmas[a] * sigmas[b] * rho
                if variance > 0:
                    sigma_port = variance ** 0.5
                    portfolio_var = sigma_port * z_var_99
                    portfolio_es = portfolio_var * 1.2

        return {
            "sharpe": baseline_sharpe,
            "var_99": portfolio_var or (var_sum or None),
            "es_99": portfolio_es or (es_sum or None),
            "weight_sum": weight_sum or None,
            "count": len(latest),
        }

    async def _latest_hub_snapshot(self, world_id: str) -> dict[str, Any] | None:
        if not self.risk_hub:
            return None
        try:
            snap = self.risk_hub.latest_snapshot(world_id)  # type: ignore[attr-defined]
            snap = await snap if inspect.isawaitable(snap) else snap
            if snap:
                payload = snap.to_dict()
                lag = None
                try:
                    ts = parse_timestamp(payload.get("as_of"))
                    if ts:
                        lag = (iso_timestamp_now_to_dt() - ts).total_seconds()
                        risk_hub_snapshot_lag_seconds.labels(world_id=world_id).set(lag)
                except Exception:
                    pass
                ref = payload.get("realized_returns_ref")
                resolver = getattr(self.risk_hub, "resolve_blob_ref", None)
                if ref and resolver is not None:
                    try:
                        realized = resolver(ref)
                        realized = await realized if inspect.isawaitable(realized) else realized
                        if realized is not None:
                            payload["realized_returns"] = realized
                    except Exception:
                        pass
                stress_ref = payload.get("stress_ref")
                if stress_ref and resolver is not None and payload.get("stress") is None:
                    try:
                        stress_payload = resolver(stress_ref)
                        stress_payload = (
                            await stress_payload
                            if inspect.isawaitable(stress_payload)
                            else stress_payload
                        )
                        if isinstance(stress_payload, Mapping):
                            payload["stress"] = dict(stress_payload)
                    except Exception:
                        pass
                return payload
            risk_hub_snapshot_missing_total.labels(world_id=world_id).inc()
            return None
        except Exception:
            return None


    @staticmethod
    def _coerce_float_series(source: Any) -> list[float] | None:
        if isinstance(source, (list, tuple)):
            try:
                return [float(v) for v in source]
            except Exception:
                return None
        return None

    @classmethod
    def _extract_live_returns(cls, realized: Any, strategy_id: str) -> list[float] | None:
        """Best-effort extraction of per-strategy live returns from realized payloads."""

        if realized is None:
            return None
        if isinstance(realized, Mapping):
            for key in (strategy_id, str(strategy_id), "live_returns", "returns"):
                if key in realized:
                    series = cls._coerce_float_series(realized.get(key))
                    if series is not None:
                        return series
            nested = realized.get("strategies")
            if isinstance(nested, Mapping) and strategy_id in nested:
                series = cls._coerce_float_series(nested.get(strategy_id))
                if series is not None:
                    return series
        return cls._coerce_float_series(realized)

    @classmethod
    def _extract_stress_for_strategy(
        cls, stress_payload: Any, strategy_id: str
    ) -> dict[str, Any] | None:
        """Best-effort extraction of per-strategy stress metrics from hub payloads.

        Supports either per-strategy buckets:
        {"s1": {"crash": {"max_drawdown": 0.2}}}
        or a shared scenario map:
        {"crash": {"max_drawdown": 0.3}}
        """

        if stress_payload is None:
            return None
        if isinstance(stress_payload, Mapping):
            direct = stress_payload.get(strategy_id)
            if isinstance(direct, Mapping):
                return dict(direct)
            nested = stress_payload.get("strategies")
            if isinstance(nested, Mapping):
                bucket = nested.get(strategy_id)
                if isinstance(bucket, Mapping):
                    return dict(bucket)
            # Treat as shared scenario map if keys look like scenarios.
            if any(isinstance(v, Mapping) for v in stress_payload.values()):
                return dict(stress_payload)
        return None


    def _baseline_from_covariance(
        self, weights: Mapping[str, float], covariance: Mapping[str, float]
    ) -> dict[str, float | int | None]:
        """Compute baseline var/es from provided weights + covariance matrix."""

        if not weights:
            return {}
        w_sum = sum(weights.values())
        if w_sum <= 0:
            return {}
        norm_weights = {k: v / w_sum for k, v in weights.items()}
        variance = 0.0
        sids = list(norm_weights.keys())
        for a in sids:
            for b in sids:
                key = f"{a},{b}"
                alt = f"{a}:{b}"
                cov_val = covariance.get(key) or covariance.get(alt)
                if cov_val is None:
                    continue
                variance += norm_weights.get(a, 0.0) * norm_weights.get(b, 0.0) * float(cov_val)
        if variance < 0:
            return {}
        if variance == 0 and covariance:
            return {"var_99": 0.0, "es_99": 0.0}
        z_var_99 = 2.33
        var_99 = (variance ** 0.5) * z_var_99
        return {"var_99": var_99, "es_99": var_99 * 1.2}

    @staticmethod
    def _extract_correlations(
        runs: Iterable[Mapping[str, Any]],
    ) -> dict[tuple[str, str], float]:
        """Extract pairwise correlations from diagnostics.extra_metrics if present."""

        correlations: dict[tuple[str, str], float] = {}
        for run in runs:
            metrics = run.get("metrics") if isinstance(run, Mapping) else {}
            diagnostics = metrics.get("diagnostics") if isinstance(metrics, Mapping) else {}
            extra = diagnostics.get("extra_metrics") if isinstance(diagnostics, Mapping) else {}
            raw = None
            if isinstance(extra, Mapping):
                raw = extra.get("pairwise_correlations") or extra.get("correlations")
            if not isinstance(raw, Mapping):
                continue
            for key, value in raw.items():
                if isinstance(value, (int, float)):
                    a: str | None = None
                    b: str | None = None
                    if isinstance(key, (tuple, list)) and len(key) == 2:
                        a, b = str(key[0]), str(key[1])
                    elif isinstance(key, str) and ":" in key:
                        a, b = key.split(":", 1)
                    if a and b:
                        correlations[(a, b)] = float(value)
                        correlations[(b, a)] = float(value)
        return correlations


def iso_timestamp_now_to_dt():
    text = iso_timestamp_now()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    from datetime import datetime

    return datetime.fromisoformat(text)


async def resolve_policy_for_extended(
    store: Storage,
    world_id: str,
    policy_payload: Any | None,
) -> Policy | None:
    """Resolve a Policy object for extended validation layers."""

    if policy_payload is None:
        try:
            return await store.get_default_policy(world_id)
        except Exception:
            logger.exception("Failed to resolve default policy for %s", world_id)
            return None

    if isinstance(policy_payload, Policy):
        return policy_payload

    try:
        if isinstance(policy_payload, Mapping) and "policy" in policy_payload:
            return Policy.model_validate(policy_payload["policy"])
        if isinstance(policy_payload, Mapping):
            return Policy.model_validate(policy_payload)
    except Exception:
        logger.exception("Failed to resolve policy for extended validation")
    return None


__all__ = ["ExtendedValidationWorker", "resolve_policy_for_extended"]
