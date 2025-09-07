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

        # Schema validation (non-breaking): accept legacy DAGs without a version
        # but standardize error reporting when an explicit unsupported version is given.
        from qmtl.dagmanager.schema_validator import validate_dag
        ok, _version, verrors = validate_dag(dag)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail={"code": "E_SCHEMA_INVALID", "errors": verrors},
            )

        from qmtl.common import crc32_of_list, compute_node_id

        crc = crc32_of_list(n.get("node_id") for n in dag.get("nodes", []))
        if crc != payload.node_ids_crc32:
            # Standardize error payload while keeping message readable
            raise HTTPException(
                status_code=400,
                detail={"code": "E_CHECKSUM_MISMATCH", "message": "node id checksum mismatch"},
            )

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
            expected = compute_node_id(*required, payload.world_id or "")
            if node.get("node_id") != expected:
                mismatches.append(
                    {"index": idx, "node_id": node.get("node_id", ""), "expected": expected}
                )
        if mismatches:
            raise HTTPException(
                status_code=400,
                detail={"code": "E_NODE_ID_MISMATCH", "node_id_mismatch": mismatches},
            )

        strategy_id, existed = await manager.submit(payload)
        if existed:
            raise HTTPException(
                status_code=409, detail={"code": "E_DUPLICATE", "strategy_id": strategy_id}
            )

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
                    dagmanager.get_queues_by_tag(
                        tags, interval, match_mode, payload.world_id
                    )
                )

        results = []
        if queries:
            results = await asyncio.gather(*queries, return_exceptions=True)

        for nid, result in zip(node_ids, results):
            if isinstance(result, Exception):
                queue_map[nid] = []
            else:
                queue_map[nid] = result

        # Try to fetch sentinel id quickly via Diff; fall back to deterministic value
        sentinel_id = f"{strategy_id}-sentinel"
        try:
            diff_task = dagmanager.diff(strategy_id, json.dumps(dag), world_id=payload.world_id)
            chunk = await asyncio.wait_for(diff_task, timeout=0.1)
            if chunk and getattr(chunk, "sentinel_id", ""):
                sentinel_id = chunk.sentinel_id
        except Exception:
            pass

        resp = StrategyAck(strategy_id=strategy_id, queue_map=queue_map, sentinel_id=sentinel_id)
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.observe_gateway_latency(duration_ms)
        return resp

    @router.post(
        "/strategies/dry-run",
        status_code=status.HTTP_200_OK,
        response_model=StrategyAck,
    )
    async def post_strategies_dry_run(payload: StrategySubmit) -> StrategyAck:
        """Dry-run submission that returns the same response shape as /strategies.

        Parity requirement: queue_map and sentinel_id semantics match the real
        submission endpoint. Implementation prefers DAG Manager diff results and
        maps them to the HTTP queue_map shape; falls back to per-node tag
        queries when diff is unavailable.
        """
        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag = json.loads(dag_bytes.decode())
        except Exception:
            dag = json.loads(payload.dag_json)

        # Schema validation parity with /strategies
        from qmtl.dagmanager.schema_validator import validate_dag
        ok, _version, verrors = validate_dag(dag)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail={"code": "E_SCHEMA_INVALID", "errors": verrors},
            )

        # Preferred path: use diff to compute sentinel and queue mapping
        sentinel_id = ""
        queue_map_http: dict[str, list[dict[str, object]]] = {}
        try:
            chunk = await asyncio.wait_for(
                dagmanager.diff("dryrun", json.dumps(dag), world_id=payload.world_id),
                timeout=0.5,
            )
            if chunk is not None:
                sentinel_id = getattr(chunk, "sentinel_id", "") or ""
                # Transform partition-key map to HTTP queue_map shape
                # Key format: "<node_id>:<interval>:<bucket>" → group by node_id
                for key, topic in dict(chunk.queue_map).items():
                    node_id = str(key).split(":", 1)[0]
                    queue_map_http.setdefault(node_id, []).append(
                        {"queue": topic, "global": False}
                    )
        except Exception:
            # Fallback: reuse TagQueryNode queries to provide parity with /strategies
            queue_map_http = {}
            node_ids: list[str] = []
            queries: list[Coroutine[Any, Any, list[str]]] = []
            for node in dag.get("nodes", []):
                if node.get("node_type") == "TagQueryNode":
                    tags = node.get("tags", [])
                    interval = int(node.get("interval", 0))
                    match_mode = node.get("match_mode", "any")
                    node_ids.append(node["node_id"])
                    queries.append(
                        dagmanager.get_queues_by_tag(
                            tags, interval, match_mode, payload.world_id
                        )
                    )
            results = []
            if queries:
                results = await asyncio.gather(*queries, return_exceptions=True)
            for nid, result in zip(node_ids, results):
                if isinstance(result, Exception):
                    queue_map_http[nid] = []
                else:
                    queue_map_http[nid] = result
            # Ensure non-empty sentinel when diff is unavailable: derive a deterministic id
            if not sentinel_id:
                from qmtl.common import crc32_of_list

                crc = crc32_of_list(n.get("node_id", "") for n in dag.get("nodes", []))
                sentinel_id = f"dryrun:{crc:08x}"

        return StrategyAck(strategy_id="dryrun", queue_map=queue_map_http, sentinel_id=sentinel_id)

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
        tags: str, interval: int, match_mode: str = "any", world_id: str = ""
    ) -> dict:
        from qmtl.common.tagquery import split_tags, normalize_match_mode
        tag_list = split_tags(tags)
        mode = normalize_match_mode(match_mode).value
        queues = await dagmanager.get_queues_by_tag(
            tag_list, interval, mode, world_id or None
        )
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
            raise HTTPException(
                status_code=403,
                detail={"code": "E_PERMISSION_DENIED", "message": "live trading not allowed"},
            )
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
