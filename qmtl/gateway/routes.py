from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
import hmac
import hashlib
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from qmtl.common.tagquery import MatchMode
from qmtl.sdk.snapshot import runtime_fingerprint

from . import metrics as gw_metrics
from .dagmanager_client import DagManagerClient
from .degradation import DegradationManager
from .event_descriptor import validate_event_token
from .gateway_health import get_health as gateway_health
from .models import (
    StrategyAck,
    StrategySubmit,
    StatusResponse,
    QueuesByTagResponse,
    ExecutionFillEvent,
)
from .strategy_manager import StrategyManager
from .strategy_submission import (
    StrategySubmissionConfig,
    StrategySubmissionHelper,
)
from .submission import SubmissionPipeline
from .ws import WebSocketHub
from .world_client import WorldServiceClient


logger = logging.getLogger(__name__)


def create_api_router(
    manager: StrategyManager,
    redis_conn,
    database_obj,
    dagmanager: DagManagerClient,
    ws_hub: Optional[WebSocketHub],
    degradation: DegradationManager,
    world_client: Optional[WorldServiceClient],
    enforce_live_guard: bool,
    fill_producer: Any | None = None,
    submission_pipeline: SubmissionPipeline | None = None,

) -> APIRouter:

    router = APIRouter()

    pipeline = submission_pipeline or SubmissionPipeline(dagmanager)
    submission_helper = StrategySubmissionHelper(
        manager, dagmanager, database_obj, pipeline=pipeline
    )

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
        result = await submission_helper.process(
            payload,
            StrategySubmissionConfig(
                submit=True,
                diff_timeout=0.1,
            ),
        )
        resp = StrategyAck(
            strategy_id=result.strategy_id,
            queue_map=result.queue_map,
            sentinel_id=result.sentinel_id,
            downgraded=result.downgraded,
            downgrade_reason=result.downgrade_reason,
            safe_mode=result.safe_mode,
        )
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
        result = await submission_helper.process(
            payload,
            StrategySubmissionConfig(
                submit=False,
                strategy_id="dryrun",
                diff_timeout=0.5,
                prefer_diff_queue_map=True,
                sentinel_default="",
                diff_strategy_id="dryrun",
                use_crc_sentinel_fallback=True,
            ),
        )
        return StrategyAck(
            strategy_id=result.strategy_id,
            queue_map=result.queue_map,
            sentinel_id=result.sentinel_id,
            downgraded=result.downgraded,
            downgrade_reason=result.downgrade_reason,
            safe_mode=result.safe_mode,
        )

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
    @router.get("/queues/by_tag", response_model=QueuesByTagResponse)
    async def queues_by_tag(
        tags: str, interval: int, match_mode: str | None = None, world_id: str = ""
    ) -> QueuesByTagResponse:
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

    async def _proxy_world_call(
        request: Request,
        func: Callable[[WorldServiceClient, dict[str, str]], Awaitable[Any]],
        *,
        response_builder: Callable[[Any, dict[str, str]], Response] | None = None,
    ) -> Response:
        client: WorldServiceClient | None = world_client
        if client is None:
            raise HTTPException(status_code=503, detail="WorldService disabled")

        headers, cid = _build_world_headers(request)
        data = await func(client, headers)

        base_headers = {"X-Correlation-ID": cid}
        builder = response_builder or (
            lambda payload, hdrs: JSONResponse(payload, headers=dict(hdrs))
        )
        return builder(data, dict(base_headers))


    @router.post("/worlds")
    async def create_world(payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.create_world(payload, headers=headers),
        )

    @router.get("/worlds")
    async def list_worlds(request: Request) -> Any:
        return await _proxy_world_call(
            request, lambda client, headers: client.list_worlds(headers=headers)
        )

    @router.get("/worlds/{world_id}")
    async def get_world(world_id: str, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.get_world(world_id, headers=headers),
        )

    @router.put("/worlds/{world_id}")
    async def put_world(world_id: str, payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.put_world(
                world_id, payload, headers=headers
            ),
        )

    @router.delete(
        "/worlds/{world_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
    )
    async def delete_world(world_id: str, request: Request) -> Response:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.delete_world(world_id, headers=headers),
            response_builder=lambda _data, headers: Response(
                status_code=status.HTTP_204_NO_CONTENT, headers=headers
            ),
        )

    @router.post("/worlds/{world_id}/policies")
    async def post_world_policy(world_id: str, payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.post_policy(
                world_id, payload, headers=headers
            ),
        )

    @router.get("/worlds/{world_id}/policies")
    async def get_world_policies(world_id: str, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.get_policies(world_id, headers=headers),
        )

    @router.post("/worlds/{world_id}/set-default")
    async def post_world_set_default(world_id: str, payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.set_default_policy(
                world_id, payload, headers=headers
            ),
        )

    @router.post("/worlds/{world_id}/bindings")
    async def post_world_bindings(world_id: str, payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.post_bindings(
                world_id, payload, headers=headers
            ),
        )

    @router.get("/worlds/{world_id}/bindings")
    async def get_world_bindings(world_id: str, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.get_bindings(world_id, headers=headers),
        )

    @router.post("/worlds/{world_id}/decisions")
    async def post_world_decisions(world_id: str, payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.post_decisions(
                world_id, payload, headers=headers
            ),
        )

    @router.put("/worlds/{world_id}/activation")
    async def put_world_activation(world_id: str, payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.put_activation(
                world_id, payload, headers=headers
            ),
        )

    @router.get("/worlds/{world_id}/audit")
    async def get_world_audit(world_id: str, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.get_audit(world_id, headers=headers),
        )
    @router.get("/worlds/{world_id}/decide")
    async def get_world_decide(world_id: str, request: Request) -> Any:
        def _response(result: Any, headers: dict[str, str]) -> Response:
            data, stale = result
            resp_headers = dict(headers)
            if stale:
                resp_headers["Warning"] = "110 - Response is stale"
                resp_headers["X-Stale"] = "true"
            return JSONResponse(data, headers=resp_headers)

        return await _proxy_world_call(
            request,
            lambda client, headers: client.get_decide(world_id, headers=headers),
            response_builder=_response,
        )

    @router.get("/worlds/{world_id}/activation")
    async def get_world_activation(world_id: str, request: Request) -> Any:
        strategy_id = request.query_params.get("strategy_id", "")
        side = request.query_params.get("side", "")

        def _response(result: Any, headers: dict[str, str]) -> Response:
            data, stale = result
            resp_headers = dict(headers)
            if stale:
                resp_headers["Warning"] = "110 - Response is stale"
                resp_headers["X-Stale"] = "true"
            return JSONResponse(data, headers=resp_headers)

        return await _proxy_world_call(
            request,
            lambda client, headers: client.get_activation(
                world_id, strategy_id, side, headers=headers
            ),
            response_builder=_response,
        )

    @router.get("/worlds/{world_id}/{topic}/state_hash")
    async def get_world_state_hash(world_id: str, topic: str, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.get_state_hash(
                world_id, topic, headers=headers
            ),
        )

    @router.post("/worlds/{world_id}/evaluate")
    async def post_world_evaluate(world_id: str, payload: dict, request: Request) -> Any:
        return await _proxy_world_call(
            request,
            lambda client, headers: client.post_evaluate(
                world_id, payload, headers=headers
            ),
        )

    @router.post("/worlds/{world_id}/apply")
    async def post_world_apply(world_id: str, payload: dict, request: Request) -> Any:
        if enforce_live_guard and request.headers.get("X-Allow-Live") != "true":
            raise HTTPException(
                status_code=403,
                detail={"code": "E_PERMISSION_DENIED", "message": "live trading not allowed"},
            )
        return await _proxy_world_call(
            request,
            lambda client, headers: client.post_apply(
                world_id, payload, headers=headers
            ),
        )

    @router.post("/fills", status_code=status.HTTP_202_ACCEPTED)
    async def post_fills(request: Request) -> Response:
        raw = await request.body()
        try:
            payload = json.loads(raw.decode())
        except Exception:
            gw_metrics.fills_rejected_total.labels(
                world_id="unknown", strategy_id="unknown", reason="invalid_json"
            ).inc()
            raise HTTPException(status_code=400, detail={"code": "E_INVALID_JSON"})

        world_id = "unknown"
        strategy_id = "unknown"
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                claims = validate_event_token(
                    token, request.app.state.event_config, audience="fills"
                )
                world_id = claims.get("world_id", world_id)
                strategy_id = claims.get("strategy_id", strategy_id)
            except Exception:
                gw_metrics.fills_rejected_total.labels(
                    world_id=world_id, strategy_id=strategy_id, reason="auth"
                ).inc()
                raise HTTPException(status_code=401, detail={"code": "E_AUTH"})
        else:
            signature = request.headers.get("X-Signature")
            secret = os.getenv("QMTL_FILL_SECRET")
            if not signature or not secret:
                gw_metrics.fills_rejected_total.labels(
                    world_id=world_id, strategy_id=strategy_id, reason="auth"
                ).inc()
                raise HTTPException(status_code=401, detail={"code": "E_AUTH"})
            expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                gw_metrics.fills_rejected_total.labels(
                    world_id=world_id, strategy_id=strategy_id, reason="auth"
                ).inc()
                raise HTTPException(status_code=401, detail={"code": "E_AUTH"})
            world_id = request.headers.get(
                "X-World-ID", payload.get("world_id", world_id)
            )
            strategy_id = request.headers.get(
                "X-Strategy-ID", payload.get("strategy_id", strategy_id)
            )

        if not world_id or not strategy_id:
            gw_metrics.fills_rejected_total.labels(
                world_id=world_id, strategy_id=strategy_id, reason="missing_ids"
            ).inc()
            raise HTTPException(status_code=400, detail={"code": "E_MISSING_IDS"})

        # Require CloudEvents 1.0 envelope; reject bare JSON
        if not (isinstance(payload, dict) and payload.get("specversion") and isinstance(payload.get("data"), dict)):
            gw_metrics.fills_rejected_total.labels(
                world_id=world_id, strategy_id=strategy_id, reason="ce_required"
            ).inc()
            raise HTTPException(status_code=400, detail={"code": "E_CE_REQUIRED", "message": "CloudEvents 1.0 envelope required with 'data' object"})
        data_obj = payload.get("data")
        # Collect standard CE headers for Kafka
        ce_headers: list[tuple[str, bytes]] = []
        for hk, rk in (
            ("ce_id", "id"),
            ("ce_type", "type"),
            ("ce_source", "source"),
            ("ce_time", "time"),
        ):
            val = payload.get(rk)
            if isinstance(val, str):
                ce_headers.append((hk, val.encode()))

        try:
            event = ExecutionFillEvent.model_validate(data_obj)
        except ValidationError as e:
            gw_metrics.fills_rejected_total.labels(
                world_id=world_id, strategy_id=strategy_id, reason="schema"
            ).inc()
            raise HTTPException(
                status_code=400,
                detail={"code": "E_SCHEMA_INVALID", "errors": e.errors()},
            )

        clean = event.model_dump()
        unknown = [k for k in payload.keys() if k not in clean]
        if unknown:
            logger.info(
                "fill_unknown_fields", extra={"event": "fill_unknown_fields", "fields": unknown}
            )

        key = f"{world_id}|{strategy_id}|{event.symbol}|{event.order_id}".encode()
        value = json.dumps(clean).encode()
        headers = [("rfp", runtime_fingerprint().encode())]
        if ce_headers:
            headers.extend(ce_headers)
        if fill_producer is not None:
            try:
                await fill_producer.send_and_wait(
                    "trade.fills", value, key=key, headers=headers
                )
            except TypeError:
                await fill_producer.send_and_wait("trade.fills", value, key=key)

        gw_metrics.fills_accepted_total.labels(
            world_id=world_id, strategy_id=strategy_id
        ).inc()
        logger.info(
            "fill_accepted",
            extra={"event": "fill_accepted", "world_id": world_id, "strategy_id": strategy_id},
        )
        return Response(status_code=status.HTTP_202_ACCEPTED)

    @router.get("/fills/replay")
    async def get_fills_replay(
        request: Request,
        start: int | None = None,
        end: int | None = None,
        world_id: str | None = None,
        strategy_id: str | None = None,
    ) -> Any:
        """Replay fills for a time window (stub).

        Returns 202 Accepted with a correlation id. Implementations may stream
        results asynchronously or trigger an offline job.
        """
        cid = uuid.uuid4().hex
        return JSONResponse(
            {
                "status": "accepted",
                "correlation_id": cid,
                "message": "replay not implemented in this build",
            },
            status_code=status.HTTP_202_ACCEPTED,
        )

    @router.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(gw_metrics.collect_metrics(), media_type="text/plain")

    return router
