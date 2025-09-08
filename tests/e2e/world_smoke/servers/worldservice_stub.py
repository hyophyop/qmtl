"""Minimal stub WorldService for service-mode smoke tests.

Endpoints implemented:
- GET /health
- POST /worlds (YAML)
- GET /worlds/{id}
- GET /worlds/{id}/decide
- GET /worlds/{id}/activation
- GET /worlds/{id}/{topic}/state_hash
- POST /worlds/{id}/evaluate
- POST /worlds/{id}/apply

This service is intentionally simplistic and stateful only in-memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, Response, Request, HTTPException
from pydantic import BaseModel
import yaml
import time


app = FastAPI()


@dataclass
class WorldRecord:
    yml: dict
    version: int = 1


WORLDS: Dict[str, WorldRecord] = {}
ETAG_COUNTER: Dict[str, int] = {}


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
async def activation(wid: str) -> Response:
    # Toggle an ETag per call sequence
    cnt = ETAG_COUNTER.get(wid, 0) + 1
    ETAG_COUNTER[wid] = cnt
    etag = f"act:{wid}:{cnt//2}"
    body = {
        "world_id": wid,
        "strategy_id": "s-demo",
        "side": "long",
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


class EvaluateRequest(BaseModel):
    as_of: str | None = None


@app.post("/worlds/{wid}/evaluate")
async def evaluate(wid: str, req: EvaluateRequest) -> dict:
    # Return a trivial plan
    return {"plan": {"activate": ["s1"], "deactivate": []}, "notes": "stub"}


class ApplyRequest(BaseModel):
    run_id: str
    plan: dict | None = None


@app.post("/worlds/{wid}/apply")
async def apply(wid: str, req: ApplyRequest) -> dict:
    return {"ok": True, "run_id": req.run_id}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=18080)


if __name__ == "__main__":
    main()

