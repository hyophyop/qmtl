"""Helper worker for extended validation layers (cohort/portfolio/stress/live)."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from qmtl.services.worldservice.policy_engine import Policy, evaluate_extended_layers

from .core_loop_hub import (
    baseline_from_covariance,
    candidate_weight_from_snapshot,
    extract_returns_from_realized,
    extract_stress_for_strategy,
    incremental_var_es_from_covariance,
)
from .live_metrics_risk import (
    risk_hub_snapshot_lag_seconds,
    risk_hub_snapshot_missing_total,
)
from .metrics import parse_timestamp
from .storage import Storage
from .validation_metrics import (
    augment_live_metrics,
    augment_portfolio_metrics,
    augment_stress_metrics,
    iso_timestamp_now,
)

logger = logging.getLogger(__name__)


class ExtendedValidationWorker:
    """Orchestrates evaluation of extended validation layers over stored runs."""

    def __init__(
        self,
        store: Storage,
        risk_hub: Any | None = None,
        *,
        windows: Iterable[int] = (30, 60, 90),
    ) -> None:
        self.store = store
        self.risk_hub = risk_hub
        self.windows = tuple(int(w) for w in windows)

    async def run(
        self,
        world_id: str,
        *,
        stage: str | None = None,
        policy_payload: Any | None = None,
        strategy_id: str | None = None,
        run_id: str | None = None,
    ) -> int:
        """Evaluate extended layers for a world and persist results."""

        policy = await resolve_policy_for_extended(self.store, world_id, policy_payload)
        if policy is None:
            return 0

        runs = await self.store.list_evaluation_runs(world_id=world_id)
        filtered = self._filter_runs(
            runs,
            stage=stage,
            strategy_id=strategy_id,
            run_id=run_id,
        )
        if not filtered:
            return 0

        hub_payload = await self._latest_hub_snapshot(world_id)
        self._enrich_runs_from_hub_payload(filtered, hub_payload, policy_payload=policy_payload)
        hub_weights, hub_covariance, baseline_from_hub, candidate_weight = self._risk_hub_portfolio_context(
            hub_payload
        )

        for run in filtered:
            await self._augment_run_with_portfolio_metrics(
                world_id,
                run,
                hub_weights=hub_weights,
                hub_covariance=hub_covariance,
                baseline_from_hub=baseline_from_hub,
                candidate_weight=candidate_weight,
            )

        extended = evaluate_extended_layers(filtered, policy, stage=stage)
        if not extended:
            return 0

        updated = 0
        for run in filtered:
            updated += await self._persist_extended_results(world_id, run, extended)
        return updated

    @staticmethod
    def _filter_runs(
        runs: list[dict[str, Any]],
        *,
        stage: str | None,
        strategy_id: str | None,
        run_id: str | None,
    ) -> list[dict[str, Any]]:
        stage_normalized = (stage or "").lower()
        filtered = [
            run
            for run in runs
            if not stage_normalized or str(run.get("stage", "")).lower() == stage_normalized
        ]
        if strategy_id:
            filtered = [run for run in filtered if str(run.get("strategy_id") or "") == str(strategy_id)]
        if run_id:
            filtered = [run for run in filtered if str(run.get("run_id") or "") == str(run_id)]
        return filtered

    def _enrich_runs_from_hub_payload(
        self,
        runs: list[dict[str, Any]],
        hub_payload: Mapping[str, Any] | None,
        *,
        policy_payload: Any | None,
    ) -> None:
        realized_payload = hub_payload.get("realized_returns") if isinstance(hub_payload, Mapping) else None
        stress_payload = hub_payload.get("stress") if isinstance(hub_payload, Mapping) else None

        for run in runs:
            sid = str(run.get("strategy_id") or "")
            if not sid:
                continue

            metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
            metrics = dict(metrics or {})

            diagnostics = metrics.get("diagnostics") if isinstance(metrics.get("diagnostics"), Mapping) else {}
            diagnostics = dict(diagnostics or {})
            if diagnostics.get("live_returns") is None and realized_payload is not None:
                live_returns = extract_returns_from_realized(realized_payload, strategy_id=sid)
                if live_returns:
                    diagnostics["live_returns"] = live_returns
                    metrics["diagnostics"] = diagnostics

            if metrics.get("stress") is None and stress_payload is not None:
                stress_for_sid = extract_stress_for_strategy(stress_payload, strategy_id=sid)
                if stress_for_sid:
                    metrics["stress"] = stress_for_sid

            if metrics:
                derived = augment_live_metrics(metrics, windows=self.windows)
                derived = augment_stress_metrics(derived, policy_payload=policy_payload)
                run["metrics"] = derived

    @staticmethod
    def _risk_hub_portfolio_context(
        hub_payload: Mapping[str, Any] | None,
    ) -> tuple[
        dict[str, Any] | None,
        dict[str, Any] | None,
        dict[str, float | int | None],
        float,
    ]:
        hub_weights = (
            dict(hub_payload.get("weights") or {})
            if isinstance(hub_payload, Mapping) and isinstance(hub_payload.get("weights"), Mapping)
            else None
        )
        hub_covariance = (
            dict(hub_payload.get("covariance") or {})
            if isinstance(hub_payload, Mapping) and isinstance(hub_payload.get("covariance"), Mapping)
            else None
        )
        baseline_from_hub = (
            baseline_from_covariance(weights=hub_weights, covariance=hub_covariance) or {}
            if hub_weights is not None and hub_covariance is not None
            else {}
        )
        candidate_weight = candidate_weight_from_snapshot(hub_payload or {})
        if candidate_weight is None:
            candidate_weight = 1.0 / float(max(len(hub_weights or {}), 0) + 1)
        return hub_weights, hub_covariance, baseline_from_hub, candidate_weight

    async def _augment_run_with_portfolio_metrics(
        self,
        world_id: str,
        run: dict[str, Any],
        *,
        hub_weights: dict[str, Any] | None,
        hub_covariance: dict[str, Any] | None,
        baseline_from_hub: Mapping[str, Any],
        candidate_weight: float,
    ) -> None:
        strategy_id = run.get("strategy_id")
        if not strategy_id:
            return
        sid = str(strategy_id)
        raw_metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
        metrics: dict[str, Any] = dict(raw_metrics or {})

        baseline = baseline_from_hub or await self._portfolio_baseline(world_id, exclude_strategy_id=sid)
        incremental = (
            incremental_var_es_from_covariance(
                weights=hub_weights,
                covariance=hub_covariance,
                candidate_id=sid,
                candidate_weight=candidate_weight,
                baseline=baseline_from_hub,
            )
            if hub_weights is not None
            and hub_covariance is not None
            and baseline_from_hub.get("var_99") is not None
            and baseline_from_hub.get("es_99") is not None
            else None
        )
        if incremental is not None:
            risk_block = metrics.get("risk") if isinstance(metrics.get("risk"), Mapping) else {}
            risk_block = dict(risk_block or {})
            risk_block["incremental_var_99"] = incremental["incremental_var_99"]
            risk_block["incremental_es_99"] = incremental["incremental_es_99"]
            metrics["risk"] = risk_block

            diagnostics = metrics.get("diagnostics") if isinstance(metrics.get("diagnostics"), Mapping) else {}
            diagnostics = dict(diagnostics or {})
            extra = diagnostics.get("extra_metrics")
            extra = dict(extra) if isinstance(extra, Mapping) else {}
            extra.setdefault("portfolio_candidate_weight", incremental["candidate_weight"])
            diagnostics["extra_metrics"] = extra
            metrics["diagnostics"] = diagnostics

        metrics = augment_portfolio_metrics(
            metrics,
            baseline_sharpe=baseline.get("sharpe") if isinstance(baseline, Mapping) else None,
            baseline_var_99=baseline.get("var_99") if isinstance(baseline, Mapping) else None,
            baseline_es_99=baseline.get("es_99") if isinstance(baseline, Mapping) else None,
        )
        run["metrics"] = metrics

    async def _persist_extended_results(
        self,
        world_id: str,
        run: dict[str, Any],
        extended: dict[str, dict[str, Any]],
    ) -> int:
        strategy_id = run.get("strategy_id")
        if not strategy_id:
            return 0
        strategy_id = str(strategy_id)
        if strategy_id not in extended:
            return 0

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

        metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
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
        return 1

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
            baseline = baseline_from_covariance(weights=weights, covariance=cov)
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
