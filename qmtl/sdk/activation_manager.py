"""Consume activation updates via the Gateway's `/events/subscribe` descriptor, bridging the internal ControlBus.

Default policy is safe: if the descriptor or resulting stream is unavailable or stale,
orders remain gated OFF (no long/short) until an activation is received.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Dict

import httpx

from .ws_client import WebSocketClient


@dataclass
class ActivationState:
    long_active: bool = False
    short_active: bool = False
    etag: Optional[str] = None


class ActivationManager:
    """Subscribe to activation updates and expose allow/deny checks."""

    def __init__(self, gateway_url: str | None = None, *, ws_client: WebSocketClient | None = None,
                 world_id: str | None = None, strategy_id: str | None = None) -> None:
        self.gateway_url = gateway_url
        self.client = ws_client
        if self.client is not None:
            self.client.on_message = self._on_message
        self.world_id = world_id
        self.strategy_id = strategy_id
        self.state = ActivationState()
        self._started = False

    def allow_side(self, side: str) -> bool:
        s = side.lower()
        if s in {"buy", "long"}:
            return self.state.long_active
        if s in {"sell", "short"}:
            return self.state.short_active
        return False

    async def _on_message(self, data: dict) -> None:
        event = data.get("event") or data.get("type")
        payload = data.get("data", data)
        if event == "activation_updated" or payload.get("type") == "ActivationUpdated":
            side = (payload.get("side") or "").lower()
            active = bool(payload.get("active", False))
            self.state.etag = payload.get("etag") or self.state.etag
            if side == "long":
                self.state.long_active = active
            elif side == "short":
                self.state.short_active = active

    async def start(self) -> None:
        if self._started:
            return
        if self.client:
            await self.client.start()
            self._started = True
            return
        if not self.gateway_url:
            return
        subscribe_url = self.gateway_url.rstrip("/") + "/events/subscribe"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                payload = {
                    "topics": ["activation"],
                    "world_id": self.world_id or "",
                    "strategy_id": self.strategy_id or "",
                }
                resp = await client.post(subscribe_url, json=payload, timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json()
                    stream_url = data.get("stream_url")
                    token = data.get("token")
                    if stream_url:
                        self.client = WebSocketClient(stream_url, on_message=self._on_message, token=token)
                        await self.client.start()
                        self._started = True
        except Exception:
            # Safe default: keep sides gated OFF until activation arrives
            return

    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
        self._started = False
