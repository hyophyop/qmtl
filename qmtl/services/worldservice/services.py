"""Public service façade orchestrating world operations."""

from __future__ import annotations

import json
import logging
import asyncio
import inspect
import math
import re
from dataclasses import dataclass
from copy import deepcopy
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional

from fastapi import HTTPException

from qmtl.model_cards import ModelCardRegistry
from qmtl.foundation.common.hashutils import hash_bytes
from qmtl.foundation.common.compute_context import canonicalize_world_mode

from .activation import ActivationEventPublisher
from .apply_flow import ApplyCoordinator
from .controlbus_producer import ControlBusProducer
from .decision import DecisionEvaluator, augment_metrics_with_linearity
from .policy import GatingPolicy
from .policy_engine import PolicyEvaluationResult, recommended_stage
from .extended_validation_worker import ExtendedValidationWorker
from .validation_metrics import (
    augment_advanced_metrics,
    augment_live_metrics,
    augment_portfolio_metrics,
    augment_stress_metrics,
)
from .rebalancing import MultiWorldProportionalRebalancer, MultiWorldRebalanceContext, PositionSlice, SymbolDelta
from .rebalancing.overlay import OverlayConfigError, OverlayPlanner
from .run_state import ApplyRunRegistry, ApplyRunState, ApplyStage
from .schemas import (
    ActivationEnvelope,
    ActivationRequest,
    AllocationUpsertRequest,
    AllocationUpsertResponse,
    ApplyAck,
    ApplyRequest,
    ApplyResponse,
    CohortEvaluateRequest,
    CohortEvaluateResponse,
    DecisionEnvelope,
    EvaluateRequest,
    ExPostFailureRecord,
    EvaluationOverride,
    MultiWorldRebalanceRequest,
    PositionSliceModel,
    SeamlessArtifactPayload,
    StrategySeries,
)
from . import metrics as ws_metrics
from .metrics import parse_timestamp
from .storage import Storage
from .validation_checks import ensure_validation_health


logger = logging.getLogger(__name__)

DEFAULT_REBALANCE_SCHEMA_VERSION = 1


@dataclass
class AllocationExecutionPlan:
    payload: AllocationUpsertRequest
    etag: str
    schema_version: int
    world_ids: tuple[str, ...]
    world_alloc_before: Dict[str, float]
    strategy_alloc_before: Dict[str, Dict[str, float]]
    plan_payload: Dict[str, Any]
    request_snapshot: Dict[str, Any]
    executed: bool = False
    execution_response: Any | None = None


@dataclass
class _DecisionState:
    """Cached decision inputs to support simple hysteresis."""

    effective_mode: str
    dataset_fingerprint: str | None = None


class WorldService:
    """Business logic helpers for the world service FastAPI application."""

    def __init__(
        self,
        store: Storage,
        bus: ControlBusProducer | None = None,
        rebalance_executor: Any | None = None,
        model_cards: ModelCardRegistry | None = None,
        extended_validation_scheduler: Callable[[Awaitable[int]], Any] | None = None,
        risk_hub: Any | None = None,
        event_driven_validation: bool = False,
    ) -> None:
        self.bus = bus
        self.rebalance_executor = rebalance_executor
        self._runs = ApplyRunRegistry()
        self.apply_runs = self._runs.runs
        self.apply_locks = self._runs.locks
        self._activation = ActivationEventPublisher(store, bus, risk_hub=risk_hub)
        self._evaluator = DecisionEvaluator(store)
        self._model_cards = model_cards or ModelCardRegistry()
        self._coordinator = ApplyCoordinator(
            store=store,
            bus=bus,
            evaluator=self._evaluator,
            activation=self._activation,
            runs=self._runs,
        )
        self.store = store
        self._allocation_locks: Dict[str, asyncio.Lock] = {}
        self._multi_rebalancer = MultiWorldProportionalRebalancer()
        self._decisions: Dict[str, _DecisionState] = {}
        self._extended_validation_scheduler = extended_validation_scheduler
        self._risk_hub = risk_hub
        self._event_driven_validation = bool(event_driven_validation)

    @staticmethod
    def _series_returns(series: StrategySeries | None) -> list[float] | None:
        if series is None:
            return None
        if series.returns:
            try:
                return [float(v) for v in series.returns]
            except Exception:
                return None
        if series.pnl:
            try:
                return [float(v) for v in series.pnl]
            except Exception:
                return None
        if series.equity and len(series.equity) >= 2:
            returns: list[float] = []
            prev: float | None = None
            for point in series.equity:
                if prev is None:
                    prev = float(point)
                    continue
                current = float(point)
                returns.append(current - prev)
                prev = current
            return returns
        return None

    def _augment_payload_metrics_with_series(self, payload: EvaluateRequest) -> None:
        metrics = payload.metrics
        if not metrics:
            return
        series = payload.series
        if not series:
            return

        augmented: dict[str, dict[str, Any]] = {}
        for sid, values in metrics.items():
            if not isinstance(values, Mapping):
                continue
            series_returns = self._series_returns(series.get(sid))
            augmented[sid] = augment_advanced_metrics(values, returns=series_returns)
        payload.metrics = augmented

    @staticmethod
    def _parse_iso_timestamp(value: Any) -> datetime:
        candidate = str(value or "").strip()
        if not candidate:
            return datetime.min.replace(tzinfo=timezone.utc)
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _pick_latest_evaluated_run_id(
        self,
        runs: list[Mapping[str, Any]],
        *,
        stage: str | None,
    ) -> str | None:
        target_stage = str(stage or "").lower().strip() or None

        def _is_evaluated(run: Mapping[str, Any]) -> bool:
            status = str(run.get("status") or "").lower().strip()
            if status == "evaluated":
                return True
            metrics = run.get("metrics")
            if isinstance(metrics, Mapping):
                return bool(metrics)
            return metrics is not None

        candidates = [r for r in runs if _is_evaluated(r)]
        if not candidates:
            return None
        if target_stage:
            stage_candidates = [
                r
                for r in candidates
                if str(r.get("stage") or "").lower().strip() == target_stage
            ]
            if stage_candidates:
                candidates = stage_candidates

        def _rank(run: Mapping[str, Any]) -> tuple[datetime, datetime]:
            updated = self._parse_iso_timestamp(run.get("updated_at"))
            created = self._parse_iso_timestamp(run.get("created_at"))
            return updated, created

        best = max(candidates, key=_rank)
        rid = str(best.get("run_id") or "").strip()
        return rid or None

    async def _fetch_latest_metrics_from_runs(
        self,
        *,
        world_id: str,
        strategy_id: str,
        stage: str | None,
    ) -> dict[str, Any] | None:
        runs_payload = await self.store.list_evaluation_runs(world_id=world_id, strategy_id=strategy_id)
        runs = [r for r in runs_payload if isinstance(r, Mapping)]
        run_id = self._pick_latest_evaluated_run_id(runs, stage=stage)
        if not run_id:
            return None
        record = await self.store.get_evaluation_run(world_id, strategy_id, run_id)
        if not isinstance(record, Mapping):
            return None
        metrics = record.get("metrics")
        if isinstance(metrics, Mapping):
            return {str(k): v for k, v in metrics.items()}
        return None

    async def _fetch_risk_hub_snapshot(
        self,
        *,
        world_id: str,
        stage: str | None,
        actor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any] | None:
        hub = getattr(self, "_risk_hub", None)
        if hub is None:
            return None

        normalized_stage = str(stage or "").strip().lower() or None
        normalized_actor = str(actor or "").strip() or None

        payload: dict[str, Any] | None = None
        if normalized_stage is None and normalized_actor is None:
            snap = hub.latest_snapshot(world_id)
            snap = await snap if inspect.isawaitable(snap) else snap
            if snap is None:
                return None
            payload = snap.to_dict() if hasattr(snap, "to_dict") else None
        else:
            listed = hub.list_snapshots(world_id, limit=max(1, int(limit or 0)))
            listed = await listed if inspect.isawaitable(listed) else listed
            if not isinstance(listed, list):
                return None
            candidates: list[dict[str, Any]] = []
            for item in listed:
                if not isinstance(item, dict):
                    continue
                prov = item.get("provenance")
                prov_map = prov if isinstance(prov, Mapping) else {}
                item_stage = str(prov_map.get("stage") or "").strip().lower()
                item_actor = str(prov_map.get("actor") or "").strip()
                if normalized_stage is not None and item_stage != normalized_stage:
                    continue
                if normalized_actor is not None and item_actor != normalized_actor:
                    continue
                candidates.append(item)
            if not candidates:
                return None

            def _rank(item: dict[str, Any]) -> tuple[datetime, datetime]:
                return (
                    self._parse_iso_timestamp(item.get("as_of")),
                    self._parse_iso_timestamp(item.get("created_at")),
                )

            payload = max(candidates, key=_rank)

        if not isinstance(payload, dict):
            return None

        resolver = getattr(hub, "resolve_blob_ref", None)
        if resolver is not None:
            for ref_key, inline_key in (
                ("covariance_ref", "covariance"),
                ("realized_returns_ref", "realized_returns"),
                ("stress_ref", "stress"),
            ):
                if payload.get(inline_key) is not None:
                    continue
                ref = payload.get(ref_key)
                if not isinstance(ref, str) or not ref:
                    continue
                try:
                    resolved = resolver(ref)
                    resolved = await resolved if inspect.isawaitable(resolved) else resolved
                    if resolved is None:
                        continue
                    if isinstance(resolved, Mapping):
                        payload[inline_key] = dict(resolved)
                    else:
                        payload[inline_key] = resolved
                except Exception:
                    continue

        return payload

    @staticmethod
    def _coerce_float_series(source: Any) -> list[float] | None:
        if isinstance(source, (list, tuple)):
            try:
                series = [float(v) for v in source]
            except Exception:
                return None
            clean = [v for v in series if math.isfinite(v)]
            return clean or None
        return None

    @classmethod
    def _extract_returns_from_realized(
        cls,
        realized: Any,
        *,
        strategy_id: str,
    ) -> list[float] | None:
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

    @staticmethod
    def _extract_stress_for_strategy(
        stress_payload: Any,
        *,
        strategy_id: str,
    ) -> dict[str, Any] | None:
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
            if any(isinstance(v, Mapping) for v in stress_payload.values()):
                return dict(stress_payload)
        return None

    @staticmethod
    def _lookup_covariance(covariance: Mapping[str, Any], a: str, b: str) -> float | None:
        for sep in (",", ":"):
            key = f"{a}{sep}{b}"
            if key in covariance:
                try:
                    value = float(covariance[key])
                except Exception:
                    value = None
                if value is not None and math.isfinite(value):
                    return value
                return None
            rev = f"{b}{sep}{a}"
            if rev in covariance:
                try:
                    value = float(covariance[rev])
                except Exception:
                    value = None
                if value is not None and math.isfinite(value):
                    return value
                return None
        return None

    @staticmethod
    def _candidate_weight_from_snapshot(snapshot: Mapping[str, Any]) -> float | None:
        constraints = snapshot.get("constraints")
        if isinstance(constraints, Mapping):
            raw = None
            for key in ("candidate_weight", "candidate_weight_default", "candidate_weight_pct"):
                if key in constraints:
                    raw = constraints.get(key)
                    if key == "candidate_weight_pct":
                        if isinstance(raw, bool):
                            raw = None
                        elif isinstance(raw, (int, float, str)):
                            try:
                                raw = float(raw) / 100.0
                            except (TypeError, ValueError):
                                raw = None
                        else:
                            raw = None
                    break
            if raw is not None:
                if isinstance(raw, bool):
                    return None
                if not isinstance(raw, (int, float, str)):
                    return None
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    return None
                if math.isfinite(value) and 0.0 < value <= 1.0:
                    return float(value)
        return None

    def _baseline_from_covariance(
        self,
        *,
        weights: Mapping[str, Any],
        covariance: Mapping[str, Any],
    ) -> dict[str, float] | None:
        if not weights or not covariance:
            return None
        w_sum = 0.0
        for value in weights.values():
            try:
                w_sum += float(value)
            except Exception:
                return None
        if w_sum <= 0:
            return None
        norm_weights = {
            str(k): float(v) / w_sum
            for k, v in weights.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        variance = 0.0
        sids = list(norm_weights.keys())
        for a in sids:
            for b in sids:
                cov_val = self._lookup_covariance(covariance, a, b)
                if cov_val is None:
                    continue
                variance += norm_weights.get(a, 0.0) * norm_weights.get(b, 0.0) * float(cov_val)
        if not (variance >= 0.0 and math.isfinite(variance)):
            return None
        z_var_99 = 2.33
        var_99 = math.sqrt(variance) * z_var_99
        if not math.isfinite(var_99):
            return None
        return {"var_99": float(var_99), "es_99": float(var_99) * 1.2}

    def _incremental_var_es_from_covariance(
        self,
        *,
        weights: Mapping[str, Any],
        covariance: Mapping[str, Any],
        candidate_id: str,
        candidate_weight: float,
        baseline: Mapping[str, Any],
    ) -> dict[str, float] | None:
        if candidate_id in weights:
            return None
        base_var = baseline.get("var_99")
        base_es = baseline.get("es_99")
        if not isinstance(base_var, (int, float)) or not isinstance(base_es, (int, float)):
            return None
        alpha = float(candidate_weight)
        if not math.isfinite(alpha) or alpha <= 0.0:
            return None
        if alpha > 1.0:
            alpha = 1.0
        if self._lookup_covariance(covariance, candidate_id, candidate_id) is None:
            return None

        scaled_existing: dict[str, float] = {}
        if alpha < 1.0:
            for sid, weight in weights.items():
                if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                    continue
                if weight == 0:
                    continue
                scaled = float(weight) * (1.0 - alpha)
                if scaled != 0:
                    scaled_existing[str(sid)] = scaled

        new_weights = dict(scaled_existing)
        new_weights[candidate_id] = alpha
        with_candidate = self._baseline_from_covariance(weights=new_weights, covariance=covariance)
        if with_candidate is None:
            return None
        with_var = with_candidate.get("var_99")
        with_es = with_candidate.get("es_99")
        if not isinstance(with_var, (int, float)) or not isinstance(with_es, (int, float)):
            return None
        return {
            "candidate_weight": float(alpha),
            "incremental_var_99": float(with_var) - float(base_var),
            "incremental_es_99": float(with_es) - float(base_es),
        }

    @staticmethod
    def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = dict(base)
        for key, value in overlay.items():
            if key in out and isinstance(out.get(key), Mapping) and isinstance(value, Mapping):
                out[key] = WorldService._deep_merge(out[key], value)
            else:
                out[key] = value
        return out

    async def _metrics_from_risk_hub(
        self,
        *,
        world_id: str,
        strategy_id: str,
        stage: str | None,
    ) -> dict[str, Any] | None:
        snapshot = await self._fetch_risk_hub_snapshot(world_id=world_id, stage=stage)
        if not snapshot:
            return None
        derived: dict[str, Any] = {}

        realized = snapshot.get("realized_returns")
        live_returns = self._extract_returns_from_realized(realized, strategy_id=strategy_id)
        if live_returns is not None:
            diagnostics = dict(derived.get("diagnostics") or {})
            diagnostics["live_returns"] = live_returns
            diagnostics.setdefault("live_returns_source", "risk_hub")
            derived["diagnostics"] = diagnostics

        stress_payload = snapshot.get("stress")
        stress = self._extract_stress_for_strategy(stress_payload, strategy_id=strategy_id)
        if stress is not None:
            derived["stress"] = stress

        weights = snapshot.get("weights")
        covariance = snapshot.get("covariance")
        if isinstance(weights, Mapping) and isinstance(covariance, Mapping) and covariance:
            baseline = self._baseline_from_covariance(weights=weights, covariance=covariance)
            if baseline:
                candidate_weight = self._candidate_weight_from_snapshot(snapshot)
                if candidate_weight is None:
                    candidate_weight = 1.0 / float(max(1, len(weights)) + 1)
                risk_metrics = self._incremental_var_es_from_covariance(
                    weights=weights,
                    covariance=covariance,
                    candidate_id=strategy_id,
                    candidate_weight=candidate_weight,
                    baseline=baseline,
                )
                if risk_metrics:
                    risk = dict(derived.get("risk") or {})
                    risk["incremental_var_99"] = risk_metrics.get("incremental_var_99")
                    risk["incremental_es_99"] = risk_metrics.get("incremental_es_99")
                    risk["candidate_weight"] = risk_metrics.get("candidate_weight")
                    derived["risk"] = risk

                    diagnostics = dict(derived.get("diagnostics") or {})
                    extra = dict(diagnostics.get("extra_metrics") or {})
                    extra.setdefault("portfolio_baseline_var_99", baseline.get("var_99"))
                    extra.setdefault("portfolio_baseline_es_99", baseline.get("es_99"))
                    extra.setdefault("risk_hub_snapshot_version", snapshot.get("version"))
                    diagnostics["extra_metrics"] = extra
                    derived["diagnostics"] = diagnostics

        return derived or None

    async def _ensure_metrics_for_evaluate(self, world_id: str, payload: EvaluateRequest) -> None:
        strategy_id = str(payload.strategy_id or "").strip() or None
        if strategy_id is None:
            return

        if "<strategy_id>" in (payload.metrics or {}) and strategy_id not in payload.metrics:
            payload.metrics[strategy_id] = payload.metrics.pop("<strategy_id>")

        existing = payload.metrics.get(strategy_id)
        if isinstance(existing, Mapping) and existing:
            return

        stage = str(payload.stage or "").strip() or None
        base_metrics = await self._fetch_latest_metrics_from_runs(
            world_id=world_id,
            strategy_id=strategy_id,
            stage=stage,
        )
        hub_metrics = await self._metrics_from_risk_hub(
            world_id=world_id,
            strategy_id=strategy_id,
            stage=stage,
        )
        if base_metrics and hub_metrics:
            derived = self._deep_merge(base_metrics, hub_metrics)
        else:
            derived = base_metrics or hub_metrics
        if derived:
            payload.metrics[strategy_id] = derived

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            candidate = float(value)
            return candidate if math.isfinite(candidate) else None
        return None

    @classmethod
    def _extract_metric(cls, metrics: Mapping[str, Any], block: str, key: str) -> float | None:
        direct = cls._coerce_float(metrics.get(key))
        if direct is not None:
            return direct
        section = metrics.get(block)
        if isinstance(section, Mapping):
            return cls._coerce_float(section.get(key))
        return None

    async def _augment_payload_metrics_with_paper_shadow_baselines(
        self,
        world_id: str,
        payload: EvaluateRequest,
    ) -> None:
        stage = (payload.stage or "").lower()
        if stage not in {"paper", "shadow"}:
            return
        metrics = payload.metrics
        if not metrics:
            return

        for sid, values in metrics.items():
            if not isinstance(values, Mapping):
                continue
            runs = await self.store.list_evaluation_runs(world_id=world_id, strategy_id=sid)
            backtests = [r for r in runs if str(r.get("stage") or "").lower() == "backtest"]
            if not backtests:
                continue

            def _rank(run: Mapping[str, Any]) -> tuple[datetime, datetime]:
                created = parse_timestamp(str(run.get("created_at") or "")) or datetime.min.replace(tzinfo=timezone.utc)
                updated = parse_timestamp(str(run.get("updated_at") or "")) or created
                return updated, created

            baseline = max(backtests, key=_rank)
            baseline_metrics = baseline.get("metrics")
            if not isinstance(baseline_metrics, Mapping):
                continue

            base_sharpe = self._extract_metric(baseline_metrics, "returns", "sharpe")
            base_dd = self._extract_metric(baseline_metrics, "returns", "max_drawdown")
            base_var = self._extract_metric(baseline_metrics, "returns", "var_p01")
            base_es = self._extract_metric(baseline_metrics, "returns", "es_p01")
            base_dd = abs(base_dd) if base_dd is not None else None

            cur_sharpe = self._extract_metric(values, "returns", "sharpe")
            cur_dd = self._extract_metric(values, "returns", "max_drawdown")
            cur_var = self._extract_metric(values, "returns", "var_p01")
            cur_es = self._extract_metric(values, "returns", "es_p01")
            cur_dd = abs(cur_dd) if cur_dd is not None else None

            diagnostics = values.get("diagnostics")
            diagnostics_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
            extra = diagnostics_map.get("extra_metrics")
            extra_map = dict(extra) if isinstance(extra, Mapping) else {}

            if base_sharpe is not None:
                extra_map.setdefault("backtest_sharpe", base_sharpe)
            if base_dd is not None:
                extra_map.setdefault("backtest_max_drawdown", base_dd)
            if base_var is not None:
                extra_map.setdefault("backtest_var_p01", base_var)
            if base_es is not None:
                extra_map.setdefault("backtest_es_p01", base_es)
            extra_map.setdefault("paper_shadow_baseline_run_id", str(baseline.get("run_id") or ""))

            if base_sharpe not in (None, 0.0) and cur_sharpe is not None:
                extra_map.setdefault("paper_vs_backtest_sharpe_ratio", cur_sharpe / base_sharpe)
            if base_dd not in (None, 0.0) and cur_dd is not None:
                extra_map.setdefault("paper_vs_backtest_dd_ratio", cur_dd / base_dd)
            if base_var not in (None, 0.0) and cur_var is not None:
                extra_map.setdefault("paper_vs_backtest_var_p01_ratio", cur_var / base_var)
            if base_es not in (None, 0.0) and cur_es is not None:
                extra_map.setdefault("paper_vs_backtest_es_p01_ratio", cur_es / base_es)

            diagnostics_map["extra_metrics"] = extra_map
            updated_values = dict(values)
            updated_values["diagnostics"] = diagnostics_map
            metrics[sid] = updated_values

    def _augment_payload_metrics_with_benchmark_comparisons(self, payload: EvaluateRequest) -> None:
        metrics = payload.metrics
        if not metrics:
            return

        for sid, values in metrics.items():
            if not isinstance(values, Mapping):
                continue
            benchmark = values.get("benchmark")
            if not isinstance(benchmark, Mapping):
                continue
            benchmark_sharpe = self._coerce_float(benchmark.get("sharpe"))
            if benchmark_sharpe is None:
                continue

            sharpe = self._extract_metric(values, "returns", "sharpe")
            diagnostics = values.get("diagnostics")
            diagnostics_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
            extra = diagnostics_map.get("extra_metrics")
            extra_map = dict(extra) if isinstance(extra, Mapping) else {}

            extra_map.setdefault("benchmark_sharpe", benchmark_sharpe)
            if sharpe is not None:
                extra_map.setdefault("vs_benchmark_sharpe", sharpe - benchmark_sharpe)

            diagnostics_map["extra_metrics"] = extra_map
            updated_values = dict(values)
            updated_values["diagnostics"] = diagnostics_map
            metrics[sid] = updated_values

    @property
    def store(self) -> Storage:
        return self._store

    @store.setter
    def store(self, value: Storage) -> None:
        self._store = value
        self._activation.store = value
        self._evaluator.store = value
        self._coordinator.store = value

    @property
    def model_cards(self) -> ModelCardRegistry:
        return self._model_cards

    @model_cards.setter
    def model_cards(self, value: ModelCardRegistry) -> None:
        self._model_cards = value

    def _allocation_lock_for(self, world_id: str) -> asyncio.Lock:
        lock = self._allocation_locks.get(world_id)
        if lock is None:
            lock = asyncio.Lock()
            self._allocation_locks[world_id] = lock
        return lock

    def _validate_allocation_payload(self, payload: AllocationUpsertRequest) -> None:
        if not payload.world_allocations:
            raise HTTPException(status_code=422, detail="world_allocations cannot be empty")
        invalid = [wid for wid, val in payload.world_allocations.items() if val < 0 or val > 1]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Allocation ratios must be between 0 and 1: {', '.join(sorted(invalid))}",
            )

    def _ensure_supported_mode(self, payload: AllocationUpsertRequest) -> None:
        requested_mode = (payload.mode or "scaling").lower()
        if requested_mode == "hybrid":
            raise HTTPException(
                status_code=501, detail="Hybrid mode is not implemented yet. Use mode='scaling' or 'overlay'."
            )
        if requested_mode == "overlay" and payload.overlay is None:
            raise HTTPException(
                status_code=422, detail="overlay config is required when mode='overlay'"
            )

    async def _build_allocation_context(
        self, payload: AllocationUpsertRequest, world_ids: list[str]
    ) -> tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
        states = await self.store.get_world_allocation_states(world_ids)
        world_alloc_before: Dict[str, float] = {
            wid: states[wid].allocation if wid in states else 0.0 for wid in world_ids
        }
        strategy_before: Dict[str, Dict[str, float]] = {}
        for wid, state in states.items():
            if state.strategy_alloc_total:
                strategy_before[wid] = dict(state.strategy_alloc_total)
        if payload.strategy_alloc_before_total:
            for wid, mapping in payload.strategy_alloc_before_total.items():
                strategy_before[wid] = dict(mapping)
        return world_alloc_before, strategy_before

    def _build_allocation_execution_plan(
        self,
        payload: AllocationUpsertRequest,
        etag: str,
        world_ids: list[str],
        world_alloc_before: Dict[str, float],
        strategy_before: Dict[str, Dict[str, float]],
    ) -> AllocationExecutionPlan:
        positions = self._convert_positions(payload.positions)
        context = MultiWorldRebalanceContext(
            total_equity=payload.total_equity,
            world_alloc_before=world_alloc_before,
            world_alloc_after=dict(payload.world_allocations),
            strategy_alloc_before_total=strategy_before or None,
            strategy_alloc_after_total=payload.strategy_alloc_after_total,
            positions=positions,
            min_trade_notional=payload.min_trade_notional or 0.0,
            lot_size_by_symbol=payload.lot_size_by_symbol,
        )
        plan_result = self._multi_rebalancer.plan(context)
        overlay_deltas = self._plan_overlay(
            payload=payload, context=context, plan_result=plan_result
        )
        plan_payload = self._serialize_plan(
            plan_result, schema_version=DEFAULT_REBALANCE_SCHEMA_VERSION
        )
        if overlay_deltas is not None:
            plan_payload["overlay_deltas"] = [
                {
                    "symbol": d.symbol,
                    "delta_qty": d.delta_qty,
                    "venue": d.venue,
                }
                for d in overlay_deltas
            ]
        request_snapshot = MultiWorldRebalanceRequest(
            total_equity=payload.total_equity,
            world_alloc_before=world_alloc_before,
            world_alloc_after=dict(payload.world_allocations),
            positions=payload.positions,
            strategy_alloc_before_total=strategy_before or None,
            strategy_alloc_after_total=payload.strategy_alloc_after_total,
            min_trade_notional=payload.min_trade_notional,
            lot_size_by_symbol=payload.lot_size_by_symbol,
            mode=payload.mode,
            overlay=payload.overlay,
            schema_version=DEFAULT_REBALANCE_SCHEMA_VERSION,
        ).model_dump(exclude_none=True)
        return AllocationExecutionPlan(
            payload=payload,
            etag=etag,
            schema_version=DEFAULT_REBALANCE_SCHEMA_VERSION,
            world_ids=tuple(world_ids),
            world_alloc_before=world_alloc_before,
            strategy_alloc_before=strategy_before,
            plan_payload=plan_payload,
            request_snapshot=request_snapshot,
        )

    async def _persist_allocation_plan(self, plan: AllocationExecutionPlan) -> None:
        await self.store.record_allocation_run(
            plan.payload.run_id,
            plan.etag,
            {
                "plan": plan.plan_payload,
                "request": plan.request_snapshot,
            },
            executed=False,
        )
        await self.store.set_world_allocations(
            plan.payload.world_allocations,
            run_id=plan.payload.run_id,
            etag=plan.etag,
            strategy_allocations=plan.payload.strategy_alloc_after_total,
        )
        await self.store.record_rebalance_plan(plan.plan_payload)
        if self.bus is not None:
            alpha_metrics = plan.plan_payload.get("alpha_metrics")
            intent = plan.plan_payload.get("rebalance_intent")
            for wid, per_plan in plan.plan_payload["per_world"].items():
                try:
                    await self.bus.publish_rebalancing_plan(
                        wid,
                        per_plan,
                        version=plan.schema_version,
                        schema_version=plan.schema_version,
                        alpha_metrics=alpha_metrics,
                        rebalance_intent=intent,
                    )
                except Exception:  # pragma: no cover - best effort
                    logger.exception("Failed to publish rebalancing plan for %s", wid)

    async def _maybe_execute_allocation_plan(
        self, plan: AllocationExecutionPlan
    ) -> AllocationExecutionPlan:
        if not plan.payload.execute:
            return plan
        response = await self._execute_rebalance(plan.request_snapshot)
        plan.execution_response = response
        plan.executed = True
        await self.store.mark_allocation_run_executed(plan.payload.run_id)
        return plan

    @asynccontextmanager
    async def _lock_worlds(self, world_ids: list[str]):
        async with AsyncExitStack() as stack:
            for wid in world_ids:
                await stack.enter_async_context(self._allocation_lock_for(wid))
            yield

    async def _plan_and_persist_allocation(
        self,
        payload: AllocationUpsertRequest,
        etag: str,
        world_ids: list[str],
        world_alloc_before: Dict[str, float],
        strategy_before: Dict[str, Dict[str, float]],
    ) -> AllocationExecutionPlan:
        plan = self._build_allocation_execution_plan(
            payload, etag, world_ids, world_alloc_before, strategy_before
        )
        await self._persist_allocation_plan(plan)
        return plan

    async def _handle_existing_allocation_run(
        self,
        payload: AllocationUpsertRequest,
        etag: str,
        existing_run: Mapping[str, Any],
    ) -> AllocationUpsertResponse:
        stored_etag = existing_run.get("etag")
        if stored_etag and stored_etag != etag:
            raise HTTPException(status_code=409, detail="run_id already used with a different payload")

        record_payload = existing_run.get("payload", {})
        plan_payload = record_payload.get("plan", record_payload)
        request_snapshot = record_payload.get("request")
        executed = bool(existing_run.get("executed", False))
        execution_response: Any | None = None

        if payload.execute and not executed:
            if request_snapshot is None:
                request_snapshot = payload.model_dump(
                    exclude={"run_id", "etag"},
                    exclude_none=True,
                )
            execution_response = await self._execute_rebalance(request_snapshot)
            await self.store.mark_allocation_run_executed(payload.run_id)
            executed = True

        return AllocationUpsertResponse(
            run_id=payload.run_id,
            etag=stored_etag or etag,
            executed=executed,
            execution_response=execution_response,
            **plan_payload,
        )

    async def evaluate(self, world_id: str, payload: EvaluateRequest) -> ApplyResponse:
        await self._ensure_metrics_for_evaluate(world_id, payload)
        try:
            self._augment_payload_metrics_with_series(payload)
        except Exception:  # pragma: no cover - best-effort enrichment
            logger.exception("Failed to derive advanced metrics for %s", world_id)
        try:
            self._augment_payload_metrics_with_benchmark_comparisons(payload)
        except Exception:  # pragma: no cover - best-effort enrichment
            logger.exception("Failed to derive benchmark comparisons for %s", world_id)
        try:
            await self._augment_payload_metrics_with_paper_shadow_baselines(world_id, payload)
        except Exception:  # pragma: no cover - best-effort enrichment
            logger.exception("Failed to derive paper/shadow baselines for %s", world_id)
        evaluation = await self._evaluator.determine_active(world_id, payload)
        active = list(evaluation)
        run_id, strategy_id = await self._maybe_record_evaluation_run(world_id, payload, evaluation)
        eval_url = (
            self._build_evaluation_run_url(world_id, strategy_id, run_id)
            if run_id and strategy_id
            else None
        )
        return ApplyResponse(
            active=active,
            evaluation_run_id=run_id,
            evaluation_run_url=eval_url,
        )

    async def evaluate_cohort(
        self, world_id: str, payload: CohortEvaluateRequest
    ) -> CohortEvaluateResponse:
        try:
            self._augment_payload_metrics_with_series(payload)
        except Exception:  # pragma: no cover - best-effort enrichment
            logger.exception("Failed to derive advanced metrics for %s", world_id)
        try:
            self._augment_payload_metrics_with_benchmark_comparisons(payload)
        except Exception:  # pragma: no cover - best-effort enrichment
            logger.exception("Failed to derive benchmark comparisons for %s", world_id)
        try:
            await self._augment_payload_metrics_with_paper_shadow_baselines(world_id, payload)
        except Exception:  # pragma: no cover - best-effort enrichment
            logger.exception("Failed to derive paper/shadow baselines for %s", world_id)

        evaluation = await self._evaluator.determine_active(world_id, payload)
        active = list(evaluation)
        stage = (payload.stage or "backtest").lower()
        run_id = payload.run_id or self._default_campaign_run_id(payload.campaign_id)
        candidates = list(payload.candidates or [])
        urls: Dict[str, str] = {}

        try:
            for strategy_id in candidates:
                await self._record_evaluation_run_for_strategy(
                    world_id=world_id,
                    payload=payload,
                    evaluation=evaluation,
                    strategy_id=strategy_id,
                    run_id=run_id,
                    campaign_id=payload.campaign_id,
                    candidates=candidates,
                )
                url = self._build_evaluation_run_url(world_id, strategy_id, run_id)
                if url is not None:
                    urls[strategy_id] = url

            if not self._event_driven_validation:
                await self._apply_extended_validation(
                    world_id=world_id,
                    stage=stage,
                    policy_payload=payload.policy,
                )
        except Exception:  # pragma: no cover - defensive best-effort
            logger.exception("Failed to record cohort evaluation runs for %s", world_id)

        return CohortEvaluateResponse(
            campaign_id=payload.campaign_id,
            run_id=run_id,
            candidates=candidates,
            active=active,
            evaluation_runs=urls,
        )

    @staticmethod
    def _summary_status_from_rule_results(
        results: Mapping[str, Any] | None,
        *,
        fallback_active: bool,
    ) -> str:
        if not results:
            return "pass" if fallback_active else "fail"

        blocking_fail = False
        any_problem = False
        for candidate in results.values():
            status_value = getattr(candidate, "status", None)
            severity_value = getattr(candidate, "severity", None)
            status = str(status_value or "").lower()
            severity = str(severity_value or "blocking").lower()
            if status == "fail":
                if severity == "blocking":
                    blocking_fail = True
                else:
                    any_problem = True
            elif status == "warn":
                any_problem = True
        if blocking_fail:
            return "fail"
        if any_problem:
            return "warn"
        return "pass"

    async def _record_evaluation_run_for_strategy(
        self,
        *,
        world_id: str,
        payload: EvaluateRequest,
        evaluation: PolicyEvaluationResult | None,
        strategy_id: str,
        run_id: str,
        campaign_id: str | None = None,
        candidates: list[str] | None = None,
    ) -> None:
        stage = (payload.stage or "backtest").lower()
        risk_tier = (payload.risk_tier or "unknown").lower()
        metrics = self._extract_metrics(payload, strategy_id)
        validation_payload = self._extract_validation_payload(payload)
        if evaluation:
            validation_payload = validation_payload or {}
            if evaluation.policy_version:
                validation_payload.setdefault("policy_version", str(evaluation.policy_version))
            if evaluation.ruleset_hash:
                validation_payload.setdefault("ruleset_hash", evaluation.ruleset_hash)
            if evaluation.profile:
                validation_payload.setdefault("profile", evaluation.profile)
        rule_results = evaluation.for_strategy(strategy_id) if evaluation else {}
        if rule_results:
            validation_payload = validation_payload or {}
            validation_payload["results"] = {
                name: result.model_dump() for name, result in rule_results.items()
            }
        metrics = ensure_validation_health(metrics, rule_results)
        metrics = augment_live_metrics(metrics)
        metrics = augment_stress_metrics(metrics, policy_payload=payload.policy)
        metrics = augment_portfolio_metrics(metrics)
        profile_hint = validation_payload.get("profile") if isinstance(validation_payload, Mapping) else None
        active_flag = strategy_id in (evaluation.selected if evaluation else [])
        recommended_stage_value = (
            evaluation.recommended_stage if evaluation else None
        ) or recommended_stage(profile_hint, stage)

        summary: Dict[str, Any] = {
            "status": self._summary_status_from_rule_results(rule_results, fallback_active=active_flag),
            "active": active_flag,
            "active_set": list(evaluation.selected if evaluation else []),
        }
        if recommended_stage_value:
            summary["recommended_stage"] = recommended_stage_value
        override = getattr(payload, "override", None)
        if override:
            summary.update(
                {
                    "override_status": override.status,
                    "override_reason": override.reason,
                    "override_actor": override.actor,
                    "override_timestamp": self._override_timestamp(override.timestamp),
                }
            )
        if campaign_id:
            summary["campaign_id"] = campaign_id
            if candidates is not None:
                summary["campaign_candidates"] = list(candidates)

        model_card_version = self._resolve_model_card_version(
            strategy_id, getattr(payload, "model_card_version", None)
        )

        await self.store.record_evaluation_run(
            world_id,
            strategy_id,
            run_id,
            stage=stage,
            risk_tier=risk_tier,
            model_card_version=model_card_version,
            metrics=metrics,
            validation=validation_payload,
            summary=summary,
        )
        if self.bus is not None:
            try:
                await self.bus.publish_evaluation_run_created(
                    world_id,
                    strategy_id=strategy_id,
                    run_id=run_id,
                    stage=stage,
                    risk_tier=risk_tier,
                    status=summary.get("status"),
                    recommended_stage=summary.get("recommended_stage"),
                )
            except Exception:  # pragma: no cover - best-effort observability
                logger.exception(
                    "Failed to publish evaluation run created event for %s/%s",
                    world_id,
                    strategy_id,
                )

    async def _maybe_record_evaluation_run(
        self,
        world_id: str,
        payload: EvaluateRequest,
        evaluation: PolicyEvaluationResult | None,
    ) -> tuple[str | None, str | None]:
        strategy_id = self._resolve_strategy_id(payload)
        if strategy_id is None:
            return None, None

        run_id = payload.run_id or self._default_evaluation_run_id(strategy_id)
        stage = (payload.stage or "backtest").lower()
        try:
            await self._record_evaluation_run_for_strategy(
                world_id=world_id,
                payload=payload,
                evaluation=evaluation,
                strategy_id=strategy_id,
                run_id=run_id,
            )
            if not self._event_driven_validation:
                await self._apply_extended_validation(
                    world_id=world_id,
                    stage=stage,
                    policy_payload=payload.policy,
                    strategy_id=strategy_id,
                    run_id=run_id,
                )
        except Exception:  # pragma: no cover - defensive best-effort
            logger.exception("Failed to record evaluation run for %s/%s", world_id, strategy_id)

        return run_id, strategy_id

    async def record_evaluation_override(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        override: EvaluationOverride,
    ) -> Dict[str, Any]:
        existing = await self.store.get_evaluation_run(world_id, strategy_id, run_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        summary = existing.get("summary") if isinstance(existing, Mapping) else {}
        if isinstance(summary, Mapping):
            current_status = str(summary.get("override_status") or "").lower()
        else:
            current_status = ""
        requested_status = str(override.status or "").lower()
        if current_status and current_status == requested_status:
            return dict(existing)
        try:
            record = await self.store.record_evaluation_override(
                world_id,
                strategy_id,
                run_id,
                override=override.model_dump(),
            )
            if self.bus is not None:
                try:
                    summary = record.get("summary") if isinstance(record, Mapping) else {}
                    revision = None
                    if isinstance(record, Mapping):
                        rev = record.get("revision")
                        if isinstance(rev, int):
                            revision = rev
                        elif isinstance(rev, str):
                            try:
                                revision = int(rev)
                            except Exception:
                                revision = None
                    await self.bus.publish_evaluation_run_updated(
                        world_id,
                        strategy_id=strategy_id,
                        run_id=run_id,
                        stage=str(record.get("stage") or ""),
                        risk_tier=str(record.get("risk_tier") or "") or None,
                        status=summary.get("status") if isinstance(summary, Mapping) else None,
                        recommended_stage=(
                            summary.get("recommended_stage") if isinstance(summary, Mapping) else None
                        ),
                        change_type="override",
                        version=revision or 1,
                    )
                except Exception:  # pragma: no cover - best-effort observability
                    logger.exception(
                        "Failed to publish evaluation run updated event for %s/%s",
                        world_id,
                        strategy_id,
                    )
            return record
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="evaluation run not found") from exc
        except Exception as exc:  # pragma: no cover - defensive best-effort
            logger.exception("Failed to record evaluation override for %s/%s", world_id, strategy_id)
            raise HTTPException(status_code=500, detail="failed to record evaluation override") from exc

    async def record_ex_post_failure(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        failure: ExPostFailureRecord,
    ) -> Dict[str, Any]:
        try:
            record = await self.store.record_ex_post_failure(
                world_id,
                strategy_id,
                run_id,
                failure=failure.model_dump(),
            )
            if self.bus is not None:
                try:
                    summary = record.get("summary") if isinstance(record, Mapping) else {}
                    revision = None
                    if isinstance(record, Mapping):
                        rev = record.get("revision")
                        if isinstance(rev, int):
                            revision = rev
                        elif isinstance(rev, str):
                            try:
                                revision = int(rev)
                            except Exception:
                                revision = None
                    await self.bus.publish_evaluation_run_updated(
                        world_id,
                        strategy_id=strategy_id,
                        run_id=run_id,
                        stage=str(record.get("stage") or ""),
                        risk_tier=str(record.get("risk_tier") or "") or None,
                        status=summary.get("status") if isinstance(summary, Mapping) else None,
                        recommended_stage=(
                            summary.get("recommended_stage") if isinstance(summary, Mapping) else None
                        ),
                        change_type="ex_post_failure",
                        version=revision or 1,
                    )
                except Exception:  # pragma: no cover - best-effort observability
                    logger.exception(
                        "Failed to publish evaluation run updated event for %s/%s",
                        world_id,
                        strategy_id,
                    )
            return record
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="evaluation run not found") from exc
        except Exception as exc:  # pragma: no cover - defensive best-effort
            logger.exception("Failed to record ex-post failure for %s/%s", world_id, strategy_id)
            raise HTTPException(status_code=500, detail="failed to record ex-post failure") from exc

    def _resolve_model_card_version(self, strategy_id: str, provided: str | None) -> str | None:
        if provided:
            return provided
        try:
            return self._model_cards.version(strategy_id)
        except Exception:  # pragma: no cover - defensive fallback
            logger.exception("Failed to resolve model card for %s", strategy_id)
            return None

    @staticmethod
    def _override_timestamp(provided: str | None) -> str:
        if provided:
            return str(provided)
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    async def _apply_extended_validation(
        self,
        *,
        world_id: str,
        stage: str | None,
        policy_payload: Any | None,
        strategy_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Apply cohort/portfolio/stress/live layers via the extended validation worker."""

        worker = ExtendedValidationWorker(self.store)
        if hasattr(self, "_risk_hub"):
            worker.risk_hub = getattr(self, "_risk_hub")

        async def _run_with_metrics() -> int:
            start = ws_metrics.monotonic_seconds()
            try:
                result = await worker.run(
                    world_id=world_id,
                    stage=stage,
                    policy_payload=policy_payload,
                    strategy_id=strategy_id,
                    run_id=run_id,
                )
            except Exception:
                ws_metrics.record_extended_validation_run(
                    world_id,
                    stage=stage,
                    status="failure",
                    latency_seconds=ws_metrics.monotonic_seconds() - start,
                )
                raise
            ws_metrics.record_extended_validation_run(
                world_id,
                stage=stage,
                status="success",
                latency_seconds=ws_metrics.monotonic_seconds() - start,
            )
            return result

        coro = _run_with_metrics()
        if self._extended_validation_scheduler:
            try:
                self._extended_validation_scheduler(coro)
                ws_metrics.record_extended_validation_run(
                    world_id,
                    stage=stage,
                    status="scheduled",
                )
            except Exception:  # pragma: no cover - defensive best-effort
                ws_metrics.record_extended_validation_run(
                    world_id,
                    stage=stage,
                    status="enqueue_failed",
                )
                coro.close()
                logger.exception("Failed to enqueue extended validation for %s", world_id)
        else:
            try:
                await coro
            except Exception:  # pragma: no cover - defensive best-effort
                logger.exception("Failed to apply extended validation layers for %s", world_id)

    @staticmethod
    def _resolve_strategy_id(payload: EvaluateRequest) -> str | None:
        if payload.strategy_id:
            return payload.strategy_id
        if payload.metrics:
            try:
                return next(iter(payload.metrics.keys()))
            except StopIteration:
                return None
        return None

    @staticmethod
    def _extract_metrics(payload: EvaluateRequest, strategy_id: str) -> dict[str, Any]:
        metrics = payload.metrics or {}
        strategy_metrics = metrics.get(strategy_id)
        if not isinstance(strategy_metrics, dict):
            return {}
        # Normalize to EvaluationMetrics shape; if already structured, pass through.
        structured_keys = {"returns", "sample", "risk", "robustness", "diagnostics"}
        if structured_keys & set(strategy_metrics.keys()):
            return deepcopy(strategy_metrics)
        return {"returns": deepcopy(strategy_metrics)}

    @staticmethod
    def _extract_validation_payload(payload: EvaluateRequest) -> dict | None:
        if payload.policy is None:
            return None
        try:
            return payload.policy.model_dump()  # type: ignore[union-attr]
        except Exception:
            return payload.policy if isinstance(payload.policy, dict) else None

    @staticmethod
    def _default_evaluation_run_id(strategy_id: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"eval-{strategy_id}-{ts}"

    @staticmethod
    def _default_campaign_run_id(campaign_id: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(campaign_id)).strip("-") or "campaign"
        return f"camp-{safe}-{ts}"

    @staticmethod
    def _build_evaluation_run_url(world_id: str, strategy_id: str | None, run_id: str | None) -> str | None:
        if strategy_id is None or run_id is None:
            return None
        return f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}"

    async def decide(self, world_id: str) -> DecisionEnvelope:
        now = datetime.now(timezone.utc)
        world = await self.store.get_world(world_id)
        if world is None:
            raise HTTPException(status_code=404, detail="world not found")

        version = await self.store.default_policy_version(world_id)
        bindings = await self.store.list_bindings(world_id)
        decisions = await self.store.get_decisions(world_id)
        metadata = await self.store.latest_history_metadata(world_id)

        normalized_metadata = self._normalize_metadata(metadata)
        allow_live = bool(world.get("allow_live", False))

        evaluation = self._evaluate_policy(
            allow_live=allow_live,
            has_bindings=bool(bindings),
            has_decisions=bool(decisions),
            metadata=normalized_metadata,
            world_id=world_id,
        )

        etag = self._build_decision_etag(
            world_id,
            version,
            normalized_metadata.get("dataset_fingerprint"),
            normalized_metadata.get("as_of"),
            normalized_metadata.get("history_updated_at"),
            now,
        )

        return DecisionEnvelope(
            world_id=world_id,
            policy_version=version,
            effective_mode=evaluation["effective_mode"],
            reason=evaluation["reason"],
            as_of=normalized_metadata.get("as_of", evaluation["as_of_fallback"]),
            ttl=evaluation["ttl"],
            etag=etag,
            dataset_fingerprint=normalized_metadata.get("dataset_fingerprint"),
            coverage_bounds=normalized_metadata.get("coverage_bounds"),
            conformance_flags=normalized_metadata.get("conformance_flags"),
            conformance_warnings=normalized_metadata.get("conformance_warnings"),
            history_updated_at=normalized_metadata.get("history_updated_at"),
            rows=normalized_metadata.get("rows"),
            artifact=normalized_metadata.get("artifact"),
        )

    async def apply(
        self,
        world_id: str,
        payload: ApplyRequest,
        gating: GatingPolicy | None,
    ) -> ApplyAck:
        lock = self._runs.lock_for(world_id)
        async with lock:
            return await self._coordinator.apply(world_id, payload, gating)

    async def upsert_activation(self, world_id: str, payload: ActivationRequest) -> ActivationEnvelope:
        data = await self._activation.upsert_activation(
            world_id, payload.model_dump(exclude_unset=True)
        )
        return ActivationEnvelope(
            world_id=world_id,
            strategy_id=payload.strategy_id,
            side=payload.side,
            **data,
        )

    @staticmethod
    def augment_metrics_with_linearity(
        metrics: Dict[str, Dict[str, float]],
        series: Dict[str, StrategySeries] | None,
    ) -> Dict[str, Dict[str, float]]:
        return augment_metrics_with_linearity(metrics, series)

    def _default_scheduler(self) -> Callable[[Awaitable[int]], Any]:
        """Fire-and-forget scheduler for extended validation tasks."""

        def schedule(coro: Awaitable[int]) -> asyncio.Task[int]:
            task = asyncio.create_task(coro)

            def _log_result(t: asyncio.Task[int]) -> None:
                try:
                    t.result()
                except Exception:  # pragma: no cover - defensive logging
                    logger.exception("Extended validation task failed")

            task.add_done_callback(_log_result)
            return task

        return schedule

    def _normalize_metadata(
        self, metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not metadata:
            return {}

        normalized: Dict[str, Any] = {}
        dataset_fp = metadata.get("dataset_fingerprint")
        if dataset_fp:
            normalized["dataset_fingerprint"] = str(dataset_fp)

        as_of_value = metadata.get("as_of")
        if as_of_value:
            normalized["as_of"] = str(as_of_value)

        updated_at = metadata.get("updated_at")
        if updated_at:
            normalized["history_updated_at"] = updated_at

        rows = metadata.get("rows")
        if rows is not None:
            try:
                normalized["rows"] = int(rows)
            except Exception:
                normalized["rows"] = rows

        raw_cov = metadata.get("coverage_bounds")
        if isinstance(raw_cov, (list, tuple)):
            normalized["coverage_bounds"] = [int(v) for v in raw_cov]

        raw_flags = metadata.get("conformance_flags")
        if isinstance(raw_flags, dict):
            normalized["conformance_flags"] = dict(raw_flags)

        raw_warnings = metadata.get("conformance_warnings")
        if raw_warnings is not None:
            normalized["conformance_warnings"] = [str(v) for v in raw_warnings]

        artifact_payload = metadata.get("artifact")
        if isinstance(artifact_payload, dict):
            normalized["artifact"] = SeamlessArtifactPayload.model_validate(
                artifact_payload
            )
            if normalized["artifact"].as_of and not normalized.get("as_of"):
                normalized["as_of"] = str(normalized["artifact"].as_of)
            if normalized.get("rows") is None and normalized["artifact"].rows is not None:
                normalized["rows"] = int(normalized["artifact"].rows)  # type: ignore[arg-type]

        return normalized

    def _evaluate_policy(
        self,
        *,
        allow_live: bool,
        has_bindings: bool,
        has_decisions: bool,
        metadata: Dict[str, Any],
        world_id: str,
    ) -> Dict[str, Any]:
        reasons: list[str] = []
        ttl = "60s"
        as_of_fallback = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        dataset_fp = metadata.get("dataset_fingerprint")
        metrics_ok = bool(
            metadata.get("coverage_bounds")
            or metadata.get("conformance_flags")
            or metadata.get("rows")
        )

        if not has_bindings:
            reasons.append("no_bindings")
            effective_mode = "validate"
        elif not has_decisions:
            reasons.append("no_active_strategies")
            effective_mode = "validate"
        else:
            reasons.append("bindings_present")
            reasons.append("decisions_present")
            hysteresis = False
            previous = self._decisions.get(world_id)
            if previous and previous.effective_mode == "live":
                hysteresis = previous.dataset_fingerprint == dataset_fp

            if allow_live and dataset_fp and metrics_ok:
                reasons.extend(["allow_live", "dataset_fingerprint_ok", "metrics_ok"])
                effective_mode = "live"
                ttl = "300s"
            elif allow_live and hysteresis:
                reasons.extend(["allow_live", "hysteresis_hold"])
                effective_mode = "live"
                ttl = "120s"
            else:
                if not allow_live:
                    reasons.append("allow_live_disabled")
                if not dataset_fp:
                    reasons.append("dataset_fingerprint_missing")
                if not metrics_ok:
                    reasons.append("required_metrics_missing")
                effective_mode = "compute-only"

        canonical_mode = canonicalize_world_mode(effective_mode)
        reason_str = " & ".join(reasons) if reasons else "unspecified"
        self._decisions[world_id] = _DecisionState(
            effective_mode=canonical_mode, dataset_fingerprint=dataset_fp
        )
        return {
            "effective_mode": canonical_mode,
            "reason": reason_str,
            "ttl": ttl,
            "as_of_fallback": as_of_fallback,
        }

    @staticmethod
    def _build_decision_etag(
        world_id: str,
        version: int,
        dataset_fp: str | None,
        as_of_value: str | None,
        updated_at: Any,
        now: datetime,
    ) -> str:
        etag_parts = [f"w:{world_id}", f"v{version}"]
        if dataset_fp:
            etag_parts.append(str(dataset_fp))
        if as_of_value:
            etag_parts.append(str(as_of_value))
        if updated_at:
            etag_parts.append(str(updated_at))
        etag_parts.append(str(int(now.timestamp())))
        return ":".join(etag_parts)

    @staticmethod
    def _hash_allocation_payload(payload: AllocationUpsertRequest) -> str:
        basis = payload.model_dump(
            exclude={"run_id", "execute", "etag"},
            exclude_none=True,
        )
        serialized = json.dumps(basis, sort_keys=True, separators=(",", ":"))
        return hash_bytes(serialized.encode("utf-8"))

    @staticmethod
    def _convert_positions(models: Iterable[PositionSliceModel]) -> list[PositionSlice]:
        return [
            PositionSlice(
                world_id=m.world_id,
                strategy_id=m.strategy_id,
                symbol=m.symbol,
                qty=m.qty,
                mark=m.mark,
                venue=m.venue,
            )
            for m in models
        ]

    @staticmethod
    def _serialize_plan(
        result,
        *,
        schema_version: int = 1,
        alpha_metrics: Dict[str, Any] | None = None,
        rebalance_intent: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        per_world: Dict[str, Any] = {}
        for wid, plan in result.per_world.items():
            per_world[wid] = {
                "world_id": wid,
                "scale_world": plan.scale_world,
                "scale_by_strategy": dict(plan.scale_by_strategy),
                "deltas": [
                    {
                        "symbol": d.symbol,
                        "delta_qty": d.delta_qty,
                        "venue": d.venue,
                    }
                    for d in plan.deltas
                ],
            }
        global_deltas = [
            {"symbol": d.symbol, "delta_qty": d.delta_qty, "venue": d.venue}
            for d in result.global_deltas
        ]
        payload: Dict[str, Any] = {
            "schema_version": schema_version,
            "per_world": per_world,
            "global_deltas": global_deltas,
        }
        if alpha_metrics is not None:
            payload["alpha_metrics"] = alpha_metrics
        if rebalance_intent is not None:
            payload["rebalance_intent"] = rebalance_intent
        return payload

    def _plan_overlay(
        self,
        *,
        payload: AllocationUpsertRequest,
        context: MultiWorldRebalanceContext,
        plan_result,
    ) -> list[SymbolDelta] | None:
        mode = (payload.mode or "scaling").lower()
        if mode != "overlay":
            return None
        if payload.overlay is None:
            raise HTTPException(
                status_code=422, detail="overlay config is required when mode='overlay'"
            )
        try:
            return OverlayPlanner().plan(
                positions=context.positions,
                world_alloc_before=context.world_alloc_before,
                world_alloc_after=context.world_alloc_after,
                overlay=payload.overlay,
                scale_by_world={wid: plan.scale_world for wid, plan in plan_result.per_world.items()},
            )
        except OverlayConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    async def _execute_rebalance(
        self,
        request_payload: Mapping[str, Any],
    ) -> Any:
        if self.rebalance_executor is None:
            raise HTTPException(status_code=503, detail="Rebalance executor not configured")
        try:
            return await self.rebalance_executor.execute(dict(request_payload))
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive propagation
            raise HTTPException(status_code=502, detail="Rebalance execution failed") from exc

    async def upsert_allocations(self, payload: AllocationUpsertRequest) -> AllocationUpsertResponse:
        self._validate_allocation_payload(payload)
        self._ensure_supported_mode(payload)

        etag = self._hash_allocation_payload(payload)
        existing_run = await self.store.get_allocation_run(payload.run_id)
        if existing_run is not None:
            return await self._handle_existing_allocation_run(payload, etag, existing_run)

        world_ids = sorted(payload.world_allocations.keys())

        async with self._lock_worlds(world_ids):
            world_alloc_before, strategy_before = await self._build_allocation_context(
                payload, world_ids
            )
            plan = await self._plan_and_persist_allocation(
                payload, etag, world_ids, world_alloc_before, strategy_before
            )
            plan = await self._maybe_execute_allocation_plan(plan)

        return AllocationUpsertResponse(
            run_id=payload.run_id,
            etag=plan.etag,
            executed=plan.executed,
            execution_response=plan.execution_response,
            **plan.plan_payload,
        )


__all__ = [
    "ApplyRunRegistry",
    "ApplyRunState",
    "ApplyStage",
    "WorldService",
]
