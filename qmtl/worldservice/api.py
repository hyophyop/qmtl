from __future__ import annotations

from typing import Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .policy_engine import Policy, evaluate_policy
from .controlbus_producer import ControlBusProducer


class ApplyRequest(BaseModel):
    policy: Policy
    metrics: Dict[str, Dict[str, float]]
    previous: List[str] | None = None
    correlations: Dict[tuple[str, str], float] | None = None


class ApplyResponse(BaseModel):
    active: List[str]


def create_app(*, bus: ControlBusProducer | None = None) -> FastAPI:
    """Return a FastAPI app exposing policy application APIs."""
    app = FastAPI()
    store: Dict[str, ApplyResponse] = {}
    policies: Dict[str, Policy] = {}

    @app.get("/worlds/{world_id}/apply", response_model=ApplyResponse)
    async def get_apply(world_id: str) -> ApplyResponse:
        if world_id not in store:
            raise HTTPException(status_code=404, detail="world not found")
        return store[world_id]

    @app.post("/worlds/{world_id}/apply", response_model=ApplyResponse)
    async def post_apply(world_id: str, payload: ApplyRequest) -> ApplyResponse:
        policy = payload.policy
        policies[world_id] = policy
        prev = payload.previous or store.get(world_id, ApplyResponse(active=[])).active
        active = evaluate_policy(payload.metrics, policy, prev, payload.correlations)
        resp = ApplyResponse(active=active)
        store[world_id] = resp
        if bus:
            await bus.publish_policy_update(world_id, active)
        return resp

    return app


__all__ = ["ApplyRequest", "ApplyResponse", "create_app"]
