from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from qmtl.sdk.node import MatchMode

from ..common.cloudevents import format_event
from .event_descriptor import (
    EventDescriptorConfig,
    jwks,
    sign_event_token,
    validate_event_token,
)
from .models import EventSubscribeRequest, EventSubscribeResponse
from .ws import WebSocketHub
from .event_models import (
    QueueUpdateData,
    SentinelWeightData,
    ActivationUpdatedData,
    PolicyUpdatedData,
    CloudEvent,
)
from . import metrics as gw_metrics

logger = logging.getLogger(__name__)


def create_event_router(
    ws_hub: WebSocketHub | None,
    event_config: EventDescriptorConfig,
    world_client: Any | None = None,
    dagmanager: Any | None = None,
) -> APIRouter:
    router = APIRouter()

    if ws_hub is not None:
        @router.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket) -> None:
            await ws_hub.connect(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                await ws_hub.disconnect(websocket)

        @router.websocket("/ws/evt")
        async def ws_evt_endpoint(websocket: WebSocket) -> None:
            topics_set: Optional[set[str]] = None
            claims: dict[str, Any] | None = None
            try:
                auth = websocket.headers.get("authorization")
                token = None
                if auth and auth.lower().startswith("bearer "):
                    token = auth.split(" ", 1)[1].strip()
                if token is None:
                    token = websocket.query_params.get("token")
                if token:
                    claims = validate_event_token(token, event_config)
                    raw_topics = claims.get("topics") or []
                    normalize = {
                        "queues": "queue",
                        "queue": "queue",
                        "activation": "activation",
                        "policy": "policy",
                    }
                    topics_set = {normalize[t] for t in raw_topics if t in normalize}
                else:
                    # Missing token
                    raise ValueError("missing token")
            except Exception:
                gw_metrics.ws_auth_failures_total.inc()
                logger.warning(
                    "ws_auth_failed",
                    extra={
                        "event": "ws_auth_failed",
                        "remote": getattr(websocket.client, "host", None),
                    },
                )
                await websocket.close(code=1008)
                return
            logger.info(
                "ws_connected",
                extra={
                    "event": "ws_connected",
                    "strategy_id": (claims or {}).get("strategy_id"),
                    "world_id": (claims or {}).get("world_id"),
                    "topics": sorted(list(topics_set or set())),
                },
            )
            gw_metrics.ws_connections_total.inc()
            await ws_hub.connect(websocket, topics=topics_set)
            # Attach world/strategy filters for scope-based gating
            try:
                await ws_hub.set_filters(
                    websocket,
                    world_id=(claims or {}).get("world_id"),
                    strategy_id=(claims or {}).get("strategy_id"),
                )
            except Exception:
                pass

            # Enqueue initial snapshot or state hash per topic
            if topics_set:
                world_id = claims.get("world_id") if claims else None
                if "queue" in topics_set and dagmanager is not None:
                    tags_param = websocket.query_params.get("tags")
                    interval_param = websocket.query_params.get("interval")
                    match_param = websocket.query_params.get("match_mode") or "any"
                    if tags_param and interval_param:
                        from qmtl.common.tagquery import split_tags, normalize_match_mode
                        try:
                            interval_int = int(interval_param)
                        except (TypeError, ValueError):
                            interval_int = None
                        tags_list = split_tags(tags_param)
                        if interval_int is not None and tags_list:
                            mode = normalize_match_mode(match_param)
                            try:
                                queues = await dagmanager.get_queues_by_tag(
                                    tags_list, interval_int, mode.value, world_id
                                )
                            except Exception:
                                queues = []
                            event = format_event(
                                "qmtl.gateway",
                                "queue_update",
                                {
                                    "tags": tags_list,
                                    "interval": interval_int,
                                    "queues": queues,
                                    "match_mode": mode.value,
                                },
                            )
                            await websocket.send_text(json.dumps(event))

                if world_id and world_client is not None:
                    if "activation" in topics_set:
                        try:
                            act_data, _ = await world_client.get_activation(world_id)
                            event = format_event(
                                "qmtl.gateway", "activation_updated", act_data
                            )
                            await websocket.send_text(json.dumps(event))
                        except Exception:
                            pass
                    if "policy" in topics_set:
                        try:
                            hash_data = await world_client.get_state_hash(
                                world_id, "policy"
                            )
                            payload = {"world_id": world_id}
                            if isinstance(hash_data, dict):
                                payload.update(hash_data)
                            event = format_event(
                                "qmtl.gateway", "policy_state_hash", payload
                            )
                            await websocket.send_text(json.dumps(event))
                        except Exception:
                            pass

            try:
                while True:
                    raw = await websocket.receive_text()
                    # Treat any incoming message as a heartbeat; try to parse ack structure
                    payload: dict[str, Any] | None = None
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        payload = None
                    if isinstance(payload, dict):
                        msg_type = payload.get("type") or payload.get("event")
                        if msg_type == "ack":
                            gw_metrics.ws_acks_total.inc()
                            logger.info(
                                "ws_ack",
                                extra={
                                    "event": "ws_ack",
                                    "last_id": payload.get("last_id"),
                                },
                            )
                            # Echo back an acknowledgement
                            try:
                                await websocket.send_text(
                                    json.dumps(
                                        {
                                            "type": "ack",
                                            "ts": datetime.now(timezone.utc).isoformat(),
                                            "last_id": payload.get("last_id"),
                                        }
                                    )
                                )
                            except Exception:
                                pass
                        else:
                            gw_metrics.ws_heartbeats_total.inc()
                            logger.debug(
                                "ws_heartbeat",
                                extra={"event": "ws_heartbeat"},
                            )
                    else:
                        gw_metrics.ws_heartbeats_total.inc()
            except WebSocketDisconnect:
                pass
            finally:
                gw_metrics.ws_disconnects_total.inc()
                logger.info("ws_disconnected", extra={"event": "ws_disconnected"})
                await ws_hub.disconnect(websocket)

    @router.post("/events/subscribe", response_model=EventSubscribeResponse)
    async def events_subscribe(
        payload: EventSubscribeRequest,
    ) -> EventSubscribeResponse:
        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=event_config.ttl)
        claims = {
            "aud": "controlbus",
            "sub": payload.strategy_id,
            "world_id": payload.world_id,
            "strategy_id": payload.strategy_id,
            "topics": payload.topics,
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        # ``kid`` is not part of the payload claims; ``sign_event_token`` writes
        # the key identifier to the JWT header.
        token = sign_event_token(claims, event_config)
        return EventSubscribeResponse(
            stream_url=event_config.stream_url,
            token=token,
            topics=payload.topics,
            expires_at=exp,
            fallback_url=event_config.fallback_url,
        )

    @router.get("/events/jwks")
    async def events_jwks() -> dict[str, Any]:
        return jwks(event_config)

    @router.get("/events/schema")
    async def events_schema() -> dict[str, Any]:
        """Return JSON Schemas for WS event payloads."""
        return {
            "queue_update": CloudEvent[QueueUpdateData].model_json_schema(),
            "sentinel_weight": CloudEvent[SentinelWeightData].model_json_schema(),
            "activation_updated": CloudEvent[ActivationUpdatedData].model_json_schema(),
            "policy_updated": CloudEvent[PolicyUpdatedData].model_json_schema(),
        }

    return router
