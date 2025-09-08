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
from . import runtime


@dataclass
class ActivationState:
    long_active: bool = False
    short_active: bool = False
    etag: Optional[str] = None
    stale: bool = True


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
        self._poll_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    def allow_side(self, side: str) -> bool:
        if self.state.stale:
            return False
        s = side.lower()
        if s in {"buy", "long"}:
            return self.state.long_active
        if s in {"sell", "short"}:
            return self.state.short_active
        return False

    def is_stale(self) -> bool:
        return self.state.stale

    async def _on_message(self, data: dict) -> None:
        event = data.get("event") or data.get("type")
        payload = data.get("data", data)
        if event == "activation_updated" or payload.get("type") == "ActivationUpdated":
            side = (payload.get("side") or "").lower()
            active = bool(payload.get("active", False))
            self.state.etag = payload.get("etag") or self.state.etag
            self.state.stale = False
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
            if self.gateway_url and self.world_id:
                self._stop_event = asyncio.Event()
                self._poll_task = asyncio.create_task(self._poll_loop())
            return
        if not self.gateway_url:
            return
        subscribe_url = self.gateway_url.rstrip("/") + "/events/subscribe"
        try:
            # Initial reconcile via HTTP so we don't rely solely on WS
            if self.world_id:
                await self._reconcile_activation()
            async with httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
                payload = {
                    "topics": ["activation"],
                    "world_id": self.world_id or "",
                    "strategy_id": self.strategy_id or "",
                }
                resp = await client.post(subscribe_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    stream_url = data.get("stream_url")
                    token = data.get("token")
                    if stream_url:
                        self.client = WebSocketClient(stream_url, on_message=self._on_message, token=token)
                        await self.client.start()
                        self._started = True
                        if self.gateway_url and self.world_id:
                            self._stop_event = asyncio.Event()
                            self._poll_task = asyncio.create_task(self._poll_loop())
        except Exception:
            # Safe default: keep sides gated OFF until activation arrives
            return

    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
        self._started = False
        if self._poll_task:
            if self._stop_event is not None:
                self._stop_event.set()
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
            self._stop_event = None

    async def _reconcile_activation(self) -> None:
        if not self.gateway_url or not self.world_id:
            return
        url = self.gateway_url.rstrip("/") + f"/worlds/{self.world_id}/activation"
        try:
            async with httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    await self._on_message({"event": "activation_updated", "data": data})
        except Exception:
            pass

    async def _poll_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await self._reconcile_activation()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=runtime.POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
