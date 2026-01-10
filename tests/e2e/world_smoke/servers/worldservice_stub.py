"""Minimal stub WorldService for service-mode smoke tests.

Endpoints implemented:
- GET /health
- POST /worlds (YAML)
- GET /worlds/{id}
- GET /worlds/{id}/decide
- GET /worlds/{id}/activation
- GET /worlds/{id}/{topic}/state_hash
- GET /allocations
- POST /worlds/{id}/evaluate
- POST /worlds/{id}/apply

This service is intentionally simplistic and stateful only in-memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

import time
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
import yaml

from qmtl.services.worldservice.shared_schemas import EvaluateRequest


app = FastAPI()


@dataclass
class WorldRecord:
    yml: dict
    version: int = 1


WORLDS: Dict[str, WorldRecord] = {}
ETAG_COUNTER: Dict[str, int] = {}
ALLOCATIONS: Dict[str, Dict[str, Any]] = {}
EVAL_RUNS: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
EVAL_ORDER: Dict[str, list[str]] = {}


def reset_state() -> None:
    WORLDS.clear()
    ETAG_COUNTER.clear()
    ALLOCATIONS.clear()
    EVAL_RUNS.clear()
    EVAL_ORDER.clear()


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/worlds")
async def create_world(request: Request) -> Response:
    raw = await request.body()
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
        wid = data.get("world", {}).get("id")
        if not wid:
            raise ValueError("missing world.id")
        WORLDS[wid] = WorldRecord(yml=data, version=WORLDS.get(wid, WorldRecord({})).version + 1)
        ETAG_COUNTER.setdefault(wid, 0)
        ALLOCATIONS.setdefault(
            wid,
            {
                "world_id": wid,
                "allocation": 1.0,
                "run_id": "alloc-stub",
                "etag": f"alloc:{wid}:1",
                "strategy_alloc_total": {"s-demo": 1.0},
                "stale": False,
            },
        )
        return Response(status_code=201)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/worlds/{wid}")
async def get_world(wid: str) -> dict:
    rec = WORLDS.get(wid)
    if not rec:
        raise HTTPException(status_code=404, detail="world not found")
    return {"world": rec.yml.get("world", {"id": wid}), "version": rec.version}


@app.get("/worlds/{wid}/decide")
async def decide(wid: str) -> Response:
    # Always return a short TTL decision with an etag
    etag = f"w:{wid}:{int(time.time())}"
    body = {
        "world_id": wid,
        "policy_version": 1,
        "effective_mode": "validate",
        "reason": "stub",
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ttl": "60s",
        "etag": etag,
    }
    return Response(content=json.dumps(body), media_type="application/json", headers={"Cache-Control": "max-age=60"})


@app.get("/worlds/{wid}/activation")
async def activation(wid: str, strategy_id: str | None = None, side: str = "long") -> Response:
    # Toggle an ETag per call sequence
    cnt = ETAG_COUNTER.get(wid, 0) + 1
    ETAG_COUNTER[wid] = cnt
    etag = f"act:{wid}:{cnt//2}"
    strategy_id_value = strategy_id or "s-demo"
    body = {
        "world_id": wid,
        "strategy_id": strategy_id_value,
        "side": side,
        "active": True,
        "weight": 1.0,
        "etag": etag,
        "run_id": f"r-{cnt}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state_hash": "h-act",
    }
    return Response(content=json.dumps(body), media_type="application/json", headers={"ETag": etag})


@app.get("/worlds/{wid}/{topic}/state_hash")
async def state_hash(wid: str, topic: str) -> dict:
    return {"state_hash": f"{topic}-hash"}


@app.get("/allocations")
async def allocations(world_id: str | None = None) -> dict:
    if world_id:
        snapshot = ALLOCATIONS.get(world_id)
        allocations = {world_id: snapshot} if snapshot else {}
    else:
        allocations = dict(ALLOCATIONS)
    return {"allocations": allocations}

@app.post("/worlds/{wid}/evaluate")
async def evaluate(wid: str, req: EvaluateRequest) -> dict:
    strategy_id = _resolve_strategy_id(req)
    if not strategy_id:
        return {
            "ok": True,
            "plan": {"activate": [], "deactivate": []},
            "notes": "stub",
        }

    run_id = req.run_id or f"run-{int(time.time())}"
    _record_eval_run(wid, strategy_id, run_id, req)

    order = EVAL_ORDER.setdefault(wid, [])
    if strategy_id not in order:
        order.append(strategy_id)

    weights = _weights_for_order(order)
    ranks = {sid: idx + 1 for idx, sid in enumerate(order)}
    contributions = {sid: round(weights.get(sid, 0.0) * 0.1, 6) for sid in order}

    return {
        "active": list(order),
        "weights": weights,
        "ranks": ranks,
        "contributions": contributions,
        "evaluation_run_id": run_id,
        "evaluation_run_url": f"/worlds/{wid}/strategies/{strategy_id}/runs/{run_id}",
        "plan": {"activate": [strategy_id], "deactivate": []},
        "notes": "stub",
    }


@app.get("/worlds/{wid}/strategies/{strategy_id}/runs/{run_id}")
async def get_evaluation_run(wid: str, strategy_id: str, run_id: str) -> dict:
    run = EVAL_RUNS.get(wid, {}).get(strategy_id, {}).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    return run


class ApplyRequest(BaseModel):
    run_id: str
    plan: dict | None = None


@app.post("/worlds/{wid}/apply")
async def apply(wid: str, req: ApplyRequest) -> dict:
    plan = req.plan or {}
    active = list(plan.get("activate", [])) if isinstance(plan, dict) else []
    return {"ok": True, "run_id": req.run_id, "active": active, "phase": "completed"}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=18080)


def _resolve_strategy_id(req: EvaluateRequest) -> str | None:
    if req.strategy_id:
        return str(req.strategy_id)
    if req.metrics:
        return str(next(iter(req.metrics.keys())))
    if req.series:
        return str(next(iter(req.series.keys())))
    return None


def _record_eval_run(wid: str, strategy_id: str, run_id: str, req: EvaluateRequest) -> None:
    payload = {
        "world_id": wid,
        "strategy_id": strategy_id,
        "run_id": run_id,
        "summary": {"status": "completed", "recommended_stage": req.stage or "validation"},
        "metrics": req.metrics.get(strategy_id, {}) if isinstance(req.metrics, dict) else {},
        "validation": {},
        "stage": req.stage,
        "risk_tier": req.risk_tier,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    EVAL_RUNS.setdefault(wid, {}).setdefault(strategy_id, {})[run_id] = payload


def _weights_for_order(order: list[str]) -> dict[str, float]:
    presets = {
        1: [1.0],
        2: [0.7, 0.3],
        3: [0.6, 0.3, 0.1],
    }
    weights = presets.get(len(order))
    if weights is None:
        if not order:
            return {}
        share = round(1.0 / len(order), 6)
        weights = [share] * len(order)
    return {sid: weights[idx] for idx, sid in enumerate(order)}


if __name__ == "__main__":
    main()
