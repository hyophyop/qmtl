from __future__ import annotations

from fastapi import FastAPI, status
from typing import Optional

from .gc import GarbageCollector
from .callbacks import post_with_backoff
from ..common.cloudevents import format_event


def create_app(gc: GarbageCollector, *, callback_url: Optional[str] = None) -> FastAPI:
    """Return a FastAPI app exposing admin routes."""
    app = FastAPI()

    @app.post("/admin/gc-trigger", status_code=status.HTTP_202_ACCEPTED)
    async def trigger_gc(payload: dict) -> dict:
        processed = gc.collect()
        if callback_url:
            event = format_event("qmtl.dagmanager", "gc", {"id": payload.get("id"), "queues": processed})
            await post_with_backoff(callback_url, event)
        return {"processed": processed}

    return app

__all__ = ["create_app"]
