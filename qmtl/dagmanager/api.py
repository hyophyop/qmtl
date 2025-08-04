from __future__ import annotations

from fastapi import FastAPI, status
from pydantic import BaseModel, Field
from typing import Optional, TYPE_CHECKING

from .gc import GarbageCollector
from .callbacks import post_with_backoff
from ..common.cloudevents import format_event
from .dagmanager_health import get_health

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
    callback_url: Optional[str] = None,
    driver: "Driver" | None = None,
) -> FastAPI:
    """Return a FastAPI app exposing admin routes."""
    app = FastAPI()

    @app.get("/status")
    async def status_endpoint() -> dict[str, str]:
        """Return system health including Neo4j connectivity."""
        return get_health(driver)

    @app.post("/admin/gc-trigger", status_code=status.HTTP_202_ACCEPTED)
    async def trigger_gc(payload: GcRequest) -> GcResponse:
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

    return app

__all__ = ["GcRequest", "GcResponse", "create_app"]
