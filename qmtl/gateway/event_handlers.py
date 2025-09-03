from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

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
            except Exception:
                await websocket.close(code=1008)
                return
            await ws_hub.connect(websocket, topics=topics_set)

            # Enqueue initial snapshot or state hash per topic
            if topics_set:
                world_id = claims.get("world_id") if claims else None
                if "queue" in topics_set and dagmanager is not None:
                    tags_param = websocket.query_params.get("tags")
                    interval_param = websocket.query_params.get("interval")
                    match_param = (
                        websocket.query_params.get("match_mode")
                        or websocket.query_params.get("match")
                        or "any"
                    )
                    if tags_param and interval_param:
                        from qmtl.common.tagquery import split_tags, normalize_match_mode
                        try:
                            interval_int = int(interval_param)
                        except (TypeError, ValueError):
                            interval_int = None
                        tags_list = split_tags(tags_param)
                        if interval_int is not None and tags_list:
                            mode = normalize_match_mode(match_param, None)
                            try:
                                queues = await dagmanager.get_queues_by_tag(
                                    tags_list, interval_int, mode.value
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
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
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

    return router
