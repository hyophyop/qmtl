"""Background worker to materialize live monitoring EvaluationRuns.

This worker consumes realized returns from Risk Signal Hub snapshots and
periodically records stage=live EvaluationRuns so that live_monitoring rules
can be evaluated over consistent artifacts.
"""

from __future__ import annotations

import logging
import inspect
from collections.abc import Mapping, Sequence
from typing import Any, Iterable

from .extended_validation_worker import ExtendedValidationWorker
from .metrics import parse_timestamp
from .validation_metrics import augment_live_metrics, iso_timestamp_now

logger = logging.getLogger(__name__)


def _safe_run_id(prefix: str, world_id: str, strategy_id: str, as_of: str) -> str:
    safe_world = str(world_id).replace("/", "-").replace(" ", "_")
    safe_strategy = str(strategy_id).replace("/", "-").replace(" ", "_")
    safe_ts = (
        str(as_of)
        .replace(":", "")
        .replace("-", "")
        .replace("T", "")
        .replace("+", "")
        .replace("Z", "")
    )
    return f"{prefix}-{safe_world}-{safe_strategy}-{safe_ts}"


def _coerce_float_series(source: Any) -> list[float] | None:
    if isinstance(source, (list, tuple)):
        try:
            return [float(v) for v in source]
        except Exception:
            return None
    return None


def _extract_live_returns(realized: Any, strategy_id: str) -> list[float] | None:
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


class LiveMonitoringWorker:
    """Generate/refresh stage=live EvaluationRuns from realized returns refs."""

    def __init__(
        self,
        store: Any,
        *,
        risk_hub: Any | None = None,
        windows: Sequence[int] = (30, 60, 90),
    ) -> None:
        self.store = store
        self.risk_hub = risk_hub
        self.windows = tuple(int(w) for w in windows)

    async def run_world(self, world_id: str) -> int:
        snapshot = await self._latest_hub_payload(world_id)
        if not snapshot:
            return 0

        as_of = str(snapshot.get("as_of") or iso_timestamp_now())
        realized = snapshot.get("realized_returns")
        if realized is None:
            return 0

        weights = snapshot.get("weights") if isinstance(snapshot.get("weights"), Mapping) else {}
        strategy_ids: Iterable[str]
        if weights:
            strategy_ids = list(weights.keys())
        else:
            try:
                strategy_ids = await self.store.get_decisions(world_id)
            except Exception:
                strategy_ids = []

        updated = 0
        for sid in strategy_ids:
            series = _extract_live_returns(realized, sid)
            if not series:
                continue

            backtest_sharpe, risk_tier, model_card_version = await self._latest_backtest_context(
                world_id, sid
            )

            metrics: dict[str, Any] = {
                "returns": {},
                "diagnostics": {"live_returns": series},
            }
            if backtest_sharpe is not None:
                metrics["returns"]["sharpe"] = backtest_sharpe

            metrics = augment_live_metrics(metrics)

            run_id = _safe_run_id("live", world_id, sid, as_of)
            try:
                await self.store.record_evaluation_run(
                    world_id,
                    sid,
                    run_id,
                    stage="live",
                    risk_tier=risk_tier or "unknown",
                    model_card_version=model_card_version,
                    metrics=metrics,
                    validation={"profile": "live_monitoring", "source": "risk_hub"},
                    summary={
                        "status": "pass",
                        "active": True,
                        "generated_by": "live_monitoring_worker",
                        "as_of": as_of,
                    },
                )
                updated += 1
            except Exception:
                logger.exception("Failed to record live monitoring run for %s/%s", world_id, sid)

        if updated and self.risk_hub is not None:
            try:
                worker = ExtendedValidationWorker(self.store, risk_hub=self.risk_hub)
                await worker.run(world_id, stage="live", policy_payload=None)
            except Exception:
                logger.exception("Failed to apply extended validation for live runs in %s", world_id)

        return updated

    async def run_all_worlds(self) -> dict[str, int]:
        try:
            worlds = await self.store.list_worlds()
        except Exception:
            worlds = []
        results: dict[str, int] = {}
        for world in worlds:
            wid = str(world.get("id") or world.get("world_id") or "")
            if not wid:
                continue
            results[wid] = await self.run_world(wid)
        return results

    async def _latest_backtest_context(
        self, world_id: str, strategy_id: str
    ) -> tuple[float | None, str | None, str | None]:
        try:
            runs = await self.store.list_evaluation_runs(world_id=world_id, strategy_id=strategy_id)
        except Exception:
            return None, None, None
        latest = None
        latest_ts = None
        for run in runs:
            if str(run.get("stage") or "").lower() == "live":
                continue
            ts = parse_timestamp(run.get("updated_at") or run.get("created_at"))
            if latest is None or (ts and (latest_ts is None or ts > latest_ts)):
                latest = run
                latest_ts = ts
        if latest is None:
            return None, None, None
        metrics = latest.get("metrics") if isinstance(latest.get("metrics"), Mapping) else {}
        returns = metrics.get("returns") if isinstance(metrics.get("returns"), Mapping) else {}
        sharpe = returns.get("sharpe")
        backtest_sharpe = float(sharpe) if isinstance(sharpe, (int, float)) else None
        return (
            backtest_sharpe,
            str(latest.get("risk_tier") or ""),
            latest.get("model_card_version"),
        )

    async def _latest_hub_payload(self, world_id: str) -> dict[str, Any] | None:
        if self.risk_hub is None:
            return None
        try:
            snap = self.risk_hub.latest_snapshot(world_id)  # type: ignore[attr-defined]
            snap = await snap if inspect.isawaitable(snap) else snap
        except Exception:
            return None
        if snap is None:
            return None
        payload = snap.to_dict()
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
        return payload


__all__ = ["LiveMonitoringWorker"]
