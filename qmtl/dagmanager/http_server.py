from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from fastapi import FastAPI, status
from pydantic import BaseModel, Field

from .callbacks import post_with_backoff
from ..common.cloudevents import format_event
from . import metrics


class WeightUpdate(BaseModel):
    version: str = Field(..., description="Version identifier")
    weight: float = Field(..., ge=0.0, le=1.0, description="Traffic weight")


if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


def create_app(
    *,
    weights: Optional[dict[str, float]] = None,
    gateway_url: str | None = None,
    driver: "Driver" | None = None,
) -> FastAPI:
    app = FastAPI()
    store = weights if weights is not None else {}

    @app.post("/callbacks/sentinel-traffic", status_code=status.HTTP_202_ACCEPTED)
    async def sentinel_traffic(update: WeightUpdate):
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
