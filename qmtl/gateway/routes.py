from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Coroutine, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from qmtl.sdk.node import MatchMode

from . import metrics as gw_metrics
from .dagmanager_client import DagManagerClient
from .degradation import DegradationManager
from .gateway_health import get_health as gateway_health
from .models import StrategyAck, StrategySubmit, StatusResponse
from .strategy_manager import StrategyManager
from .ws import WebSocketHub
from .world_client import WorldServiceClient


def create_api_router(
    manager: StrategyManager,
    redis_conn,
    database_obj,
    dagmanager: DagManagerClient,
    ws_hub: Optional[WebSocketHub],
    degradation: DegradationManager,
    world_client: Optional[WorldServiceClient],
    enforce_live_guard: bool,

) -> APIRouter:

    router = APIRouter()

    @router.get("/status")
    async def status_endpoint() -> dict[str, Any]:
        health_data = await gateway_health(
            redis_conn, database_obj, dagmanager, world_client
        )
        health_data["degrade_level"] = degradation.level.name
        health_data["enforce_live_guard"] = enforce_live_guard
        # Include basic pre-trade rejection metrics for quick visibility
        try:
            health_data["pretrade"] = gw_metrics.get_pretrade_stats()
        except Exception:
            pass
        return health_data

    @router.get("/health")
    async def health() -> dict[str, str]:
        return await gateway_health(
            redis_conn, database_obj, dagmanager, world_client
        )

    @router.post(
        "/strategies",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=StrategyAck,
    )
    async def post_strategies(payload: StrategySubmit) -> StrategyAck:
        start = time.perf_counter()
        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag = json.loads(dag_bytes.decode())
        except Exception:
            dag = json.loads(payload.dag_json)

        from qmtl.common import crc32_of_list, compute_node_id

        crc = crc32_of_list(n.get("node_id") for n in dag.get("nodes", []))
        if crc != payload.node_ids_crc32:
            raise HTTPException(status_code=400, detail="node id checksum mismatch")

        mismatches: list[dict[str, str | int]] = []
        for idx, node in enumerate(dag.get("nodes", [])):
            if node.get("node_type") == "TagQueryNode":
                continue
            required = (
                node.get("node_type"),
                node.get("code_hash"),
                node.get("config_hash"),
                node.get("schema_hash"),
            )
            if not all(required):
                continue
            expected = compute_node_id(*required)
            if node.get("node_id") != expected:
                mismatches.append(
                    {"index": idx, "node_id": node.get("node_id", ""), "expected": expected}
                )
        if mismatches:
            raise HTTPException(status_code=400, detail={"node_id_mismatch": mismatches})

        strategy_id, existed = await manager.submit(payload)
        if existed:
            raise HTTPException(status_code=409, detail={"strategy_id": strategy_id})

        queue_map: dict[str, list[str] | str] = {}
        node_ids: list[str] = []
        queries: list[Coroutine[Any, Any, list[str]]] = []
        for node in dag.get("nodes", []):
            if node.get("node_type") == "TagQueryNode":
                tags = node.get("tags", [])
                interval = int(node.get("interval", 0))
                match_mode = node.get("match_mode", "any")
                node_ids.append(node["node_id"])
                queries.append(
                    dagmanager.get_queues_by_tag(tags, interval, match_mode)
                )

        results = []
        if queries:
            results = await asyncio.gather(*queries, return_exceptions=True)

        for nid, result in zip(node_ids, results):
            if isinstance(result, Exception):
                queue_map[nid] = []
            else:
                queue_map[nid] = result

        resp = StrategyAck(strategy_id=strategy_id, queue_map=queue_map)
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.observe_gateway_latency(duration_ms)
        return resp

    @router.get(
        "/strategies/{strategy_id}/status", response_model=StatusResponse
    )
    async def get_status(strategy_id: str) -> StatusResponse:
        status_value = await manager.status(strategy_id)
        if status_value is None:
            raise HTTPException(status_code=404, detail="strategy not found")
        return StatusResponse(status=status_value)

    # Legacy DAG/Gateway callback routes have been removed in favor of
    # ControlBus-driven updates; see qmtl.gateway.ws and event handlers.
    @router.get("/queues/by_tag")
    async def queues_by_tag(
        tags: str, interval: int, match_mode: str = "any"
    ) -> dict:
        from qmtl.common.tagquery import split_tags, normalize_match_mode
        tag_list = split_tags(tags)
        mode = normalize_match_mode(match_mode).value
        queues = await dagmanager.get_queues_by_tag(tag_list, interval, mode)
        return {"queues": queues}
    def _build_world_headers(request: Request) -> tuple[dict[str, str], str]:
        headers: dict[str, str] = {}
        auth = request.headers.get("authorization")
        if auth:
            headers["Authorization"] = auth
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1]
                try:
                    parts = token.split(".")
                    if len(parts) > 1:
                        payload_b64 = parts[1]
                        padding = "=" * (-len(payload_b64) % 4)
                        payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode()
                        claims = json.loads(payload_json)
                        sub = claims.get("sub")
                        if sub is not None:
                            headers["X-Caller-Sub"] = str(sub)
                        headers["X-Caller-Claims"] = json.dumps(claims)
                except Exception:
                    pass
        roles = request.headers.get("x-world-roles")
        if roles:
            headers["X-World-Roles"] = roles
        cid = uuid.uuid4().hex
        headers["X-Correlation-ID"] = cid
        return headers, cid

    @router.get("/worlds/{world_id}/decide")
    async def get_world_decide(world_id: str, request: Request) -> Any:
        client: WorldServiceClient | None = world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers, cid = _build_world_headers(request)
        data, stale = await client.get_decide(world_id, headers=headers)
        resp_headers = {"X-Correlation-ID": cid}
        if stale:
            resp_headers["Warning"] = "110 - Response is stale"
            resp_headers["X-Stale"] = "true"
        return JSONResponse(data, headers=resp_headers)

    @router.get("/worlds/{world_id}/activation")
    async def get_world_activation(world_id: str, request: Request) -> Any:
        client: WorldServiceClient | None = world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers, cid = _build_world_headers(request)
        data, stale = await client.get_activation(world_id, headers=headers)
        resp_headers = {"X-Correlation-ID": cid}
        if stale:
            resp_headers["Warning"] = "110 - Response is stale"
            resp_headers["X-Stale"] = "true"
        return JSONResponse(data, headers=resp_headers)

    @router.get("/worlds/{world_id}/{topic}/state_hash")
    async def get_world_state_hash(world_id: str, topic: str, request: Request) -> Any:
        client: WorldServiceClient | None = world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers, cid = _build_world_headers(request)
        data = await client.get_state_hash(world_id, topic, headers=headers)
        return JSONResponse(data, headers={"X-Correlation-ID": cid})

    @router.post("/worlds/{world_id}/evaluate")
    async def post_world_evaluate(world_id: str, payload: dict, request: Request) -> Any:
        client: WorldServiceClient | None = world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers, cid = _build_world_headers(request)
        data = await client.post_evaluate(world_id, payload, headers=headers)
        return JSONResponse(data, headers={"X-Correlation-ID": cid})

    @router.post("/worlds/{world_id}/apply")
    async def post_world_apply(world_id: str, payload: dict, request: Request) -> Any:
        if enforce_live_guard and request.headers.get("X-Allow-Live") != "true":
            raise HTTPException(status_code=403, detail="live trading not allowed")
        client: WorldServiceClient | None = world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers, cid = _build_world_headers(request)
        data = await client.post_apply(world_id, payload, headers=headers)
        return JSONResponse(data, headers={"X-Correlation-ID": cid})

    @router.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(gw_metrics.collect_metrics(), media_type="text/plain")

    return router
