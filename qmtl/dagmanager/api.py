from __future__ import annotations

from fastapi import FastAPI, status
from pydantic import BaseModel, Field
from typing import Optional

from .gc import GarbageCollector
from .callbacks import post_with_backoff
from ..common.cloudevents import format_event


class GcRequest(BaseModel):
    """Payload for manual GC trigger."""

    id: str = Field(..., description="Sentinel identifier")


class GcResponse(BaseModel):
    processed: list[str]


def create_app(gc: GarbageCollector, *, callback_url: Optional[str] = None) -> FastAPI:
    """Return a FastAPI app exposing admin routes."""
    app = FastAPI()

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
