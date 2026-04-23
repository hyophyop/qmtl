from __future__ import annotations

import inspect
import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from qmtl.runtime.sdk.world_validation_metrics import build_v1_evaluation_metrics

from .controlbus_producer import ControlBusProducer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskSnapshotDispatchOutcome:
    bus_published: bool | None = None
    validation_scheduled: bool | None = None

    @property
    def completed(self) -> bool:
        return self.bus_published is not False and self.validation_scheduled is not False


def deep_merge_mappings(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if key in out and isinstance(out.get(key), Mapping) and isinstance(value, Mapping):
            out[key] = deep_merge_mappings(out[key], value)
        else:
            out[key] = value
    return out


def _coerce_float_series(source: Any) -> list[float] | None:
    if isinstance(source, (list, tuple)):
        try:
            series = [float(v) for v in source]
        except Exception:
            return None
        clean = [v for v in series if math.isfinite(v)]
        return clean or None
    return None


def extract_returns_from_realized(realized: Any, *, strategy_id: str) -> list[float] | None:
    if realized is None:
        return None
    if isinstance(realized, Mapping):
        for key in (strategy_id, str(strategy_id), "live_returns", "returns"):
            if key in realized:
                series = _coerce_float_series(realized.get(key))
                if series is not None:
                    return series
        nested = realized.get("strategies")
        if isinstance(nested, Mapping) and strategy_id in nested:
            series = _coerce_float_series(nested.get(strategy_id))
            if series is not None:
                return series
    return _coerce_float_series(realized)


def extract_stress_for_strategy(stress_payload: Any, *, strategy_id: str) -> dict[str, Any] | None:
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


def lookup_covariance(covariance: Mapping[str, Any], a: str, b: str) -> float | None:
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


def candidate_weight_from_snapshot(snapshot: Mapping[str, Any]) -> float | None:
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


def baseline_from_covariance(
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
    norm_weights: dict[str, float] = {}
    for key, value in weights.items():
        try:
            coerced = float(value)
        except Exception:
            return None
        if not math.isfinite(coerced):
            return None
        norm_weights[str(key)] = coerced / w_sum
    variance = 0.0
    sids = list(norm_weights.keys())
    for a in sids:
        for b in sids:
            cov_val = lookup_covariance(covariance, a, b)
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


def incremental_var_es_from_covariance(
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
    if lookup_covariance(covariance, candidate_id, candidate_id) is None:
        return None

    scaled_existing: dict[str, float] = {}
    if alpha < 1.0:
        for sid, weight in weights.items():
            try:
                coerced = float(weight)
            except Exception:
                return None
            if not math.isfinite(coerced):
                return None
            if coerced == 0:
                continue
            scaled = coerced * (1.0 - alpha)
            if scaled != 0:
                scaled_existing[str(sid)] = scaled

    new_weights = dict(scaled_existing)
    new_weights[candidate_id] = alpha
    with_candidate = baseline_from_covariance(weights=new_weights, covariance=covariance)
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


def derive_metrics_from_risk_snapshot(
    snapshot: Mapping[str, Any],
    *,
    strategy_id: str,
    stage: str | None = None,
) -> dict[str, Any] | None:
    derived: dict[str, Any] = {}

    realized = snapshot.get("realized_returns")
    live_returns = extract_returns_from_realized(realized, strategy_id=strategy_id)
    normalized_stage = str(stage or "").strip().lower() or None
    if normalized_stage is None:
        provenance = snapshot.get("provenance")
        if isinstance(provenance, Mapping):
            normalized_stage = str(provenance.get("stage") or "").strip().lower() or None

    if live_returns is not None:
        diagnostics = dict(derived.get("diagnostics") or {})
        diagnostics["live_returns"] = live_returns
        diagnostics.setdefault("live_returns_source", "risk_hub")
        derived["diagnostics"] = diagnostics

        if normalized_stage in {"paper", "shadow", "live", "dryrun"}:
            perf_metrics = build_v1_evaluation_metrics(
                live_returns,
                returns_source="risk_hub.realized_returns",
            )
            derived = deep_merge_mappings(derived, perf_metrics)

    stress_payload = snapshot.get("stress")
    stress = extract_stress_for_strategy(stress_payload, strategy_id=strategy_id)
    if stress is not None:
        derived["stress"] = stress

    weights = snapshot.get("weights")
    covariance = snapshot.get("covariance")
    if isinstance(weights, Mapping) and isinstance(covariance, Mapping) and covariance:
        baseline = baseline_from_covariance(weights=weights, covariance=covariance)
        if baseline:
            candidate_weight = candidate_weight_from_snapshot(snapshot)
            if candidate_weight is None:
                candidate_weight = 1.0 / float(max(1, len(weights)) + 1)
            risk_metrics = incremental_var_es_from_covariance(
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

    if derived:
        diagnostics = dict(derived.get("diagnostics") or {})
        extra = dict(diagnostics.get("extra_metrics") or {})
        extra.setdefault("risk_hub_snapshot_version", snapshot.get("version"))
        diagnostics["extra_metrics"] = extra
        derived["diagnostics"] = diagnostics

    return derived or None


class CoreLoopHub:
    """Own core-loop routing and metrics behavior adjacent to the Risk Signal Hub."""

    def __init__(
        self,
        *,
        bus: ControlBusProducer | None = None,
        schedule_extended_validation: Callable[[str], Awaitable[Any]] | Callable[[str], Any] | None = None,
    ) -> None:
        self._bus = bus
        self._schedule_extended_validation = schedule_extended_validation

    def bind_bus(self, bus: ControlBusProducer | None) -> None:
        self._bus = bus

    def bind_schedule_extended_validation(
        self,
        schedule_extended_validation: Callable[[str], Awaitable[Any]] | Callable[[str], Any] | None,
    ) -> None:
        self._schedule_extended_validation = schedule_extended_validation

    async def handle_risk_snapshot_update(
        self,
        world_id: str,
        snapshot: Mapping[str, Any],
    ) -> RiskSnapshotDispatchOutcome:
        bus_published: bool | None = None
        if self._bus is not None:
            try:
                await self._bus.publish_risk_snapshot_updated(world_id, dict(snapshot))
                bus_published = True
            except Exception:  # pragma: no cover - best-effort logging
                bus_published = False
                logger.exception("Failed to publish risk snapshot to ControlBus")
        validation_scheduled: bool | None = None
        if self._schedule_extended_validation is not None:
            try:
                maybe = self._schedule_extended_validation(world_id)
                if inspect.isawaitable(maybe):
                    await maybe
                validation_scheduled = True
            except Exception:  # pragma: no cover - best-effort logging
                validation_scheduled = False
                logger.exception("Failed to schedule extended validation from risk hub update")
        return RiskSnapshotDispatchOutcome(
            bus_published=bus_published,
            validation_scheduled=validation_scheduled,
        )


__all__ = [
    "CoreLoopHub",
    "RiskSnapshotDispatchOutcome",
    "deep_merge_mappings",
    "derive_metrics_from_risk_snapshot",
]
