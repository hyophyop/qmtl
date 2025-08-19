from __future__ import annotations

from fastapi import FastAPI, status
from pydantic import BaseModel, Field
from typing import Optional, TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from qmtl.common.tracing import setup_tracing
from .garbage_collector import GarbageCollector
from .callbacks import post_with_backoff
from ..common.cloudevents import format_event
from .dagmanager_health import get_health
from . import metrics
from .neo4j_metrics import GraphCountCollector, GraphCountScheduler

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


class GcRequest(BaseModel):
    """Payload for manual GC trigger."""

    id: str = Field(..., description="Sentinel identifier")


class GcResponse(BaseModel):
    processed: list[str]


class WeightUpdate(BaseModel):
    """Payload to update traffic weight for a version sentinel."""

    version: str = Field(..., description="Version identifier")
    weight: float = Field(
        ..., ge=0.0, le=1.0, description="Traffic weight"
    )


def create_app(
    gc: GarbageCollector,
    *,
    callback_url: Optional[str] = None,
    driver: "Driver" | None = None,
    weights: Optional[dict[str, float]] = None,
    gateway_url: str | None = None,
) -> FastAPI:
    """Return a FastAPI app exposing admin routes."""
    setup_tracing("dagmanager")
    app = FastAPI()
    FastAPIInstrumentor().instrument_app(app)

    node_count_scheduler: GraphCountScheduler | None = None
    if driver is not None:
        collector = GraphCountCollector(driver)
        node_count_scheduler = GraphCountScheduler(collector)

        async def _start_node_count_scheduler() -> None:
            await node_count_scheduler.start()

        async def _stop_node_count_scheduler() -> None:
            await node_count_scheduler.stop()

        app.add_event_handler("startup", _start_node_count_scheduler)
        app.add_event_handler("shutdown", _stop_node_count_scheduler)

    @app.get("/status")
    async def status_endpoint() -> dict[str, str]:
        """Return system health including Neo4j connectivity."""
        return get_health(driver)

    tracer = trace.get_tracer(__name__)

    @app.post("/admin/gc-trigger", status_code=status.HTTP_202_ACCEPTED)
    async def trigger_gc(payload: GcRequest) -> GcResponse:
        with tracer.start_as_current_span("dagmanager.gc_trigger"):
            infos = gc.collect()
            processed = [q.name for q in infos]
            if callback_url:
                event = format_event(
                    "qmtl.dagmanager",
                    "gc",
                    {"id": payload.id, "queues": processed},
                )
                await post_with_backoff(callback_url, event)
            return GcResponse(processed=processed)

    store = weights if weights is not None else {}

    @app.post("/callbacks/sentinel-traffic", status_code=status.HTTP_202_ACCEPTED)
    async def sentinel_traffic(update: WeightUpdate):
        with tracer.start_as_current_span("dagmanager.sentinel_weight"):
            store[update.version] = update.weight
            metrics.set_active_version_weight(update.version, update.weight)
            if driver:
                with driver.session() as session:
                    session.run(
                        "MERGE (s:VersionSentinel {version: $version}) "
                        "SET s.traffic_weight = $weight",
                        version=update.version,
                        weight=update.weight,
                    )
            if gateway_url:
                event = format_event(
                    "qmtl.dagmanager",
                    "sentinel_weight",
                    {"sentinel_id": update.version, "weight": update.weight},
                )
                await post_with_backoff(gateway_url, event)
            return {"version": update.version, "weight": update.weight}

    return app

__all__ = ["GcRequest", "GcResponse", "WeightUpdate", "create_app"]
