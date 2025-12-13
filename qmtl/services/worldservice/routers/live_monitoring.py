from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter

from .. import metrics as ws_metrics
from ..schemas import LiveMonitoringReport, LiveMonitoringStrategyReport, RuleResultModel
from ..services import WorldService
from ..live_monitoring_worker import LiveMonitoringWorker
from ..validation_metrics import iso_timestamp_now


def create_live_monitoring_router(service: WorldService) -> APIRouter:
    router = APIRouter(tags=["live-monitoring"])

    @router.get(
        "/worlds/{world_id}/live-monitoring/report",
        response_model=LiveMonitoringReport,
    )
    async def get_live_monitoring_report(world_id: str) -> LiveMonitoringReport:
        runs = await service.store.list_evaluation_runs(world_id=world_id)
        live_runs = [r for r in runs if str(r.get("stage") or "").lower() == "live"]

        latest_by_strategy: dict[str, dict[str, Any]] = {}
        for run in live_runs:
            sid = str(run.get("strategy_id") or "")
            if not sid:
                continue
            ts = str(run.get("updated_at") or run.get("created_at") or "")
            prev = latest_by_strategy.get(sid)
            prev_ts = str(prev.get("updated_at") or prev.get("created_at") or "") if prev else ""
            if prev is None or ts >= prev_ts:
                latest_by_strategy[sid] = run

        strategies: list[LiveMonitoringStrategyReport] = []
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for sid, run in sorted(latest_by_strategy.items()):
            validation = run.get("validation") if isinstance(run.get("validation"), Mapping) else {}
            results = validation.get("results") if isinstance(validation.get("results"), Mapping) else {}
            live_result_payload = results.get("live_monitoring") if isinstance(results, Mapping) else None
            live_result = (
                RuleResultModel(**live_result_payload)
                if isinstance(live_result_payload, Mapping)
                else None
            )
            if live_result is not None:
                counts[live_result.status] = counts.get(live_result.status, 0) + 1
            metrics = run.get("metrics") if isinstance(run.get("metrics"), Mapping) else {}
            diagnostics = metrics.get("diagnostics") if isinstance(metrics.get("diagnostics"), Mapping) else None
            summary = run.get("summary") if isinstance(run.get("summary"), Mapping) else {}
            as_of = summary.get("as_of") or diagnostics.get("as_of") if isinstance(diagnostics, Mapping) else None
            strategies.append(
                LiveMonitoringStrategyReport(
                    strategy_id=sid,
                    run_id=str(run.get("run_id") or ""),
                    as_of=str(as_of) if as_of else None,
                    diagnostics=dict(diagnostics) if isinstance(diagnostics, Mapping) else None,
                    live_monitoring=live_result,
                )
            )

        return LiveMonitoringReport(
            world_id=world_id,
            generated_at=iso_timestamp_now(),
            strategies=strategies,
            summary={"counts": counts, "total": len(strategies)},
        )

    @router.post("/worlds/{world_id}/live-monitoring/run")
    async def post_live_monitoring_run(world_id: str) -> dict[str, Any]:
        worker = LiveMonitoringWorker(
            service.store,
            risk_hub=getattr(service, "_risk_hub", None),
        )
        try:
            updated = await worker.run_world(world_id)
        except Exception:  # pragma: no cover - defensive
            ws_metrics.record_live_monitoring_run(world_id, status="failure")
            raise
        ws_metrics.record_live_monitoring_run(
            world_id,
            status="success",
            updated_strategies=updated,
        )
        return {"world_id": world_id, "updated": updated}

    @router.post("/worlds/live-monitoring/run-all")
    async def post_live_monitoring_run_all() -> dict[str, Any]:
        worker = LiveMonitoringWorker(
            service.store,
            risk_hub=getattr(service, "_risk_hub", None),
        )
        try:
            results = await worker.run_all_worlds()
        except Exception:  # pragma: no cover - defensive
            ws_metrics.record_live_monitoring_run("all", status="failure")
            raise
        for wid, updated in results.items():
            ws_metrics.record_live_monitoring_run(
                wid,
                status="success",
                updated_strategies=updated,
            )
        return {"results": results}

    return router


__all__ = ["create_live_monitoring_router"]
