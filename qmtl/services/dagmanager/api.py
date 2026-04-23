from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, status
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, Field

from .controlbus_producer import ControlBusProducer
from .dagmanager_health import get_health
from .garbage_collector import GarbageCollector
from .neo4j_metrics import GraphCountCollector, GraphCountScheduler
from .queue_updates import publish_queue_updates
from .repository import NodeRepository

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


class GcRequest(BaseModel):
    """Payload for manual GC trigger."""

    id: str = Field(..., description="Sentinel identifier")


class GcResponse(BaseModel):
    processed: list[str]
    report: dict[str, object] | None = None


def create_app(
    gc: GarbageCollector,
    *,
    driver: "Driver" | None = None,
    bus: ControlBusProducer | None = None,
    repo: NodeRepository | None = None,
    enable_otel: bool | None = None,
) -> FastAPI:
    """Return a FastAPI app exposing admin routes."""
    app = FastAPI()
    if enable_otel:
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
            report = gc.collect_report()
            processed = [q.name for q in report.processed]
            if bus and report.processed:
                await publish_queue_updates(
                    bus,
                    report.processed,
                    repo=repo,
                    lifecycle_items=report.items,
                )
            return GcResponse(processed=processed, report=report.to_dict())

    return app

__all__ = ["GcRequest", "GcResponse", "create_app"]
