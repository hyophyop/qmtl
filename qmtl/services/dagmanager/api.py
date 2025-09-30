from __future__ import annotations

from fastapi import FastAPI, status
from pydantic import BaseModel, Field
from typing import Optional, TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from qmtl.foundation.common.tracing import setup_tracing
from .garbage_collector import GarbageCollector
from .dagmanager_health import get_health
from .neo4j_metrics import GraphCountCollector, GraphCountScheduler
from .controlbus_producer import ControlBusProducer

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


class GcRequest(BaseModel):
    """Payload for manual GC trigger."""

    id: str = Field(..., description="Sentinel identifier")


class GcResponse(BaseModel):
    processed: list[str]


def create_app(
    gc: GarbageCollector,
    *,
    driver: "Driver" | None = None,
    bus: ControlBusProducer | None = None,
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
            if bus:
                for qi in infos:
                    if getattr(qi, "interval", None) is not None:
                        await bus.publish_queue_update(
                            [qi.tag],
                            qi.interval,
                            [qi.name],
                            "any",
                        )
            return GcResponse(processed=processed)

    return app

__all__ = ["GcRequest", "GcResponse", "create_app"]
