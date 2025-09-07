from __future__ import annotations

import asyncio
import httpx
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from .node import MatchMode
from qmtl.common.tagquery import split_tags, normalize_match_mode, normalize_queues

from .ws_client import WebSocketClient
from . import runtime
from . import runtime

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .node import TagQueryNode


class TagQueryManager:
    """Manage :class:`TagQueryNode` instances and deliver updates.

    Queue updates are received via the ControlBus-backed WebSocket from
    ``/events/subscribe``.
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        *,
        ws_client: WebSocketClient | None = None,
        world_id: str | None = None,
        strategy_id: str | None = None,
    ) -> None:
        self.gateway_url = gateway_url
        self.client = ws_client
        if self.client is not None:
            self.client.on_message = self.handle_message
        self.world_id = world_id
        self.strategy_id = strategy_id
        self._nodes: Dict[Tuple[Tuple[str, ...], int, MatchMode], List[TagQueryNode]] = {}
        self._poll_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # Best-effort idempotency for queue_update events: remember last
        # applied queue set per (tags, interval, match_mode) key to drop
        # duplicates that may occur during reconnects/retries.
        self._last_queue_sets: Dict[
            Tuple[Tuple[str, ...], int, MatchMode], frozenset[str]
        ] = {}

    # ------------------------------------------------------------------
    def register(self, node: TagQueryNode) -> None:
        key = (tuple(sorted(node.query_tags)), node.interval, node.match_mode)
        self._nodes.setdefault(key, []).append(node)

    def unregister(self, node: TagQueryNode) -> None:
        key = (tuple(sorted(node.query_tags)), node.interval, node.match_mode)
        lst = self._nodes.get(key)
        if lst and node in lst:
            lst.remove(node)
            if not lst:
                self._nodes.pop(key, None)

    # ------------------------------------------------------------------
    async def resolve_tags(self, *, offline: bool = False) -> None:
        """Resolve all registered nodes via the Gateway API."""
        if offline or not self.gateway_url:
            for nodes in self._nodes.values():
                for n in nodes:
                    n.update_queues([])
            return

        url = self.gateway_url.rstrip("/") + "/queues/by_tag"
        async with httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
            for (tags, interval, match_mode), nodes in self._nodes.items():
                params = {
                    "tags": ",".join(tags),
                    "interval": interval,
                    "match_mode": match_mode.value,
                    "world_id": self.world_id or "",
                }
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    raw = resp.json().get("queues", [])
                except httpx.RequestError:
                    raw = []
                queues = normalize_queues(raw)
                for n in nodes:
                    n.update_queues(list(queues))

    # ------------------------------------------------------------------
    async def handle_message(self, data: dict) -> None:
        """Apply WebSocket ``data`` to registered nodes."""
        event = data.get("event") or data.get("type")
        payload = data.get("data", data)
        if event == "queue_update":
            tags = payload.get("tags") or []
            interval = payload.get("interval")
            raw = payload.get("queues", [])
            queues = normalize_queues(raw)
            try:
                match_mode = normalize_match_mode(payload.get("match_mode"))
            except ValueError:
                return
            if isinstance(tags, str):
                tags = split_tags(tags)
            try:
                interval = int(interval)
            except (TypeError, ValueError):
                return
            key = (tuple(sorted(tags)), interval, match_mode)
            # Idempotency: drop duplicate updates with identical queue sets
            qset = frozenset(queues)
            last = self._last_queue_sets.get(key)
            if last is not None and last == qset:
                return
            self._last_queue_sets[key] = qset
            for n in self._nodes.get(key, []):
                n.update_queues(list(queues))

    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self.client:
            await self.client.start()
            if self.gateway_url:
                self._stop_event.clear()
                self._poll_task = asyncio.create_task(self._poll_loop())
            return
        if not self.gateway_url:
            return

        subscribe_url = self.gateway_url.rstrip("/") + "/events/subscribe"
        try:
            async with httpx.AsyncClient(timeout=runtime.HTTP_TIMEOUT_SECONDS) as client:
                topic = (
                    f"w/{self.world_id}/queues" if self.world_id else "queues"
                )
                payload = {
                    "topics": [topic],
                    "world_id": self.world_id or "",
                    "strategy_id": self.strategy_id or "",
                }
                resp = await client.post(subscribe_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    stream_url = data.get("stream_url")
                    token = data.get("token")
                    if stream_url:
                        self.client = WebSocketClient(
                            stream_url, on_message=self.handle_message, token=token
                        )
                        await self.client.start()
                        # Start periodic reconcile loop for explicit status queries
                        self._stop_event.clear()
                        self._poll_task = asyncio.create_task(self._poll_loop())
                        return
        except Exception:
            return

        if self.client:
            await self.client.start()
            # Start reconcile loop even if WS path was injected
            if self.gateway_url:
                self._stop_event.clear()
                self._poll_task = asyncio.create_task(self._poll_loop())
            return

        # No legacy watch fallback; WebSocket is required
    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
        if self._poll_task:
            self._stop_event.set()
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    async def _poll_loop(self) -> None:
        # Periodically reconcile tag queries via HTTP GET to avoid depending
        # solely on WS events. Uses the same /queues/by_tag endpoint.
        while not self._stop_event.is_set():
            try:
                await self.resolve_tags(offline=False)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=runtime.POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
