"""Consume activation updates via the Gateway's `/events/subscribe` descriptor, bridging the internal ControlBus.

Default policy is safe: if the descriptor or resulting stream is unavailable or stale,
orders remain gated OFF (no long/short) until an activation is received.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .ws_client import WebSocketClient
from . import runtime


@dataclass
class SideState:
    active: bool = False
    weight: float = 1.0
    freeze: bool = False
    drain: bool = False


@dataclass
class ActivationState:
    version: int = 0
    long: SideState = field(default_factory=SideState)
    short: SideState = field(default_factory=SideState)
    freeze: bool = False
    drain: bool = False
    etag: Optional[str] = None
    run_id: Optional[str] = None
    ts: Optional[str] = None
    state_hash: Optional[str] = None
    effective_mode: Optional[str] = None
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
        if self.state.freeze or self.state.drain:
            return False
        s = side.lower()
        st: SideState | None = None
        if s in {"buy", "long"}:
            st = self.state.long
        elif s in {"sell", "short"}:
            st = self.state.short
        if st is None:
            return False
        if st.freeze or st.drain:
            return False
        return bool(st.active)

    def is_stale(self) -> bool:
        return self.state.stale

    def weight_for_side(self, side: str) -> float:
        """Return weight [0..1] for the given side, honoring freeze/drain.

        Safe default is 0.0 when stale or side is unknown/disabled.
        """
        if self.state.stale:
            return 0.0
        if self.state.freeze or self.state.drain:
            return 0.0
        s = side.lower()
        st: SideState | None = None
        if s in {"buy", "long"}:
            st = self.state.long
        elif s in {"sell", "short"}:
            st = self.state.short
        if st is None:
            return 0.0
        if st.freeze or st.drain:
            return 0.0
        if not st.active:
            return 0.0
        w = float(st.weight)
        # Clamp to [0,1]
        if w < 0.0:
            return 0.0
        if w > 1.0:
            return 1.0
        return w

    def _recompute_global_modes(self) -> None:
        self.state.freeze = bool(self.state.long.freeze or self.state.short.freeze)
        self.state.drain = bool(self.state.long.drain or self.state.short.drain)

    async def _on_message(self, data: dict) -> None:
        payload = self._extract_activation_payload(data)
        if payload is None:
            return

        self._update_activation_metadata(payload)

        side = (payload.get("side") or "").lower()
        target = self._select_side_state(side)
        active = bool(payload.get("active", False))
        freeze = self._normalize_flag(payload.get("freeze"))
        drain = self._normalize_flag(payload.get("drain"))
        weight = self._normalize_weight(payload.get("weight"), active)

        if target is not None:
            self._apply_side_update(target, active, freeze, drain, weight)
        else:
            self._apply_global_update(freeze, drain)

        self.state.stale = False
        self._recompute_global_modes()

    def _extract_activation_payload(self, data: dict) -> dict | None:
        event = data.get("event") or data.get("type")
        payload = data.get("data", data)
        if not isinstance(payload, dict):
            return None
        if event == "activation_updated" or payload.get("type") == "ActivationUpdated":
            return payload
        return None

    def _update_activation_metadata(self, payload: dict) -> None:
        self.state.etag = payload.get("etag") or self.state.etag
        self.state.run_id = payload.get("run_id") or self.state.run_id
        self.state.ts = payload.get("ts") or self.state.ts
        self.state.state_hash = payload.get("state_hash") or self.state.state_hash
        eff_mode = payload.get("effective_mode")
        if eff_mode:
            self.state.effective_mode = eff_mode

        ver = payload.get("version")
        if ver is not None:
            try:
                self.state.version = int(ver)
            except (TypeError, ValueError):
                pass

    def _select_side_state(self, side: str) -> SideState | None:
        if side == "long":
            return self.state.long
        if side == "short":
            return self.state.short
        return None

    def _normalize_flag(self, value: object | None) -> bool | None:
        if value is None:
            return None
        return bool(value)

    def _normalize_weight(self, weight: object | None, active: bool) -> float | None:
        if weight is None:
            return 1.0 if active else 0.0
        try:
            return float(weight)
        except (TypeError, ValueError):
            return None

    def _apply_side_update(
        self,
        target: SideState,
        active: bool,
        freeze: bool | None,
        drain: bool | None,
        weight: float | None,
    ) -> None:
        target.active = active
        if freeze is not None:
            target.freeze = freeze
        if drain is not None:
            target.drain = drain
        if weight is not None:
            target.weight = weight

    def _apply_global_update(self, freeze: bool | None, drain: bool | None) -> None:
        if freeze is not None:
            self.state.long.freeze = freeze
            self.state.short.freeze = freeze
        if drain is not None:
            self.state.long.drain = drain
            self.state.short.drain = drain

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
        base = self.gateway_url.rstrip("/") + f"/worlds/{self.world_id}/activation"
        if not self.strategy_id:
            return
        try:
            async with httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
                for side in ("long", "short"):
                    resp = await client.get(base, params={"strategy_id": self.strategy_id, "side": side})
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
