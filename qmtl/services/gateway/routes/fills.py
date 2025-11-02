from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from qmtl.services.gateway import metrics as gw_metrics
from qmtl.services.gateway.event_descriptor import validate_event_token
from qmtl.services.gateway.models import ExecutionFillEvent
from qmtl.runtime.sdk.snapshot import runtime_fingerprint

from .dependencies import GatewayDependencyProvider


logger = logging.getLogger(__name__)


def create_router(deps: GatewayDependencyProvider) -> APIRouter:
    router = APIRouter()

    @router.post("/fills", status_code=status.HTTP_202_ACCEPTED)
    async def post_fills(
        request: Request,
        fill_producer: Any | None = Depends(deps.provide_fill_producer),
    ) -> Response:
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

        if not (
            isinstance(payload, dict)
            and payload.get("specversion")
            and isinstance(payload.get("data"), dict)
        ):
            gw_metrics.fills_rejected_total.labels(
                world_id=world_id, strategy_id=strategy_id, reason="ce_required"
            ).inc()
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "E_CE_REQUIRED",
                    "message": "CloudEvents 1.0 envelope required with 'data' object",
                },
            )
        data_obj = payload.get("data")

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
                "fill_unknown_fields",
                extra={"event": "fill_unknown_fields", "fields": unknown},
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
        start: int | None = None,
        end: int | None = None,
        world_id: str | None = None,
        strategy_id: str | None = None,
    ) -> Any:
        cid = uuid.uuid4().hex
        return JSONResponse(
            {
                "status": "accepted",
                "correlation_id": cid,
                "message": "replay not implemented in this build",
            },
            status_code=status.HTTP_202_ACCEPTED,
        )

    return router


__all__ = ["create_router"]
