from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .event_descriptor import (
    EventDescriptorConfig,
    jwks,
    sign_event_token,
    validate_event_token,
)
from .models import EventSubscribeRequest, EventSubscribeResponse
from .ws import WebSocketHub


def create_event_router(
    ws_hub: WebSocketHub | None, event_config: EventDescriptorConfig
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
