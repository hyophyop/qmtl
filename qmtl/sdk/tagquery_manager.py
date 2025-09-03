from __future__ import annotations

import httpx
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from .node import MatchMode
from qmtl.common.tagquery import split_tags, normalize_match_mode, normalize_queues

from .ws_client import WebSocketClient

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
        async with httpx.AsyncClient() as client:
            for (tags, interval, match_mode), nodes in self._nodes.items():
                params = {
                    "tags": ",".join(tags),
                    "interval": interval,
                    "match_mode": match_mode.value,
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
            for n in self._nodes.get(key, []):
                n.update_queues(list(queues))

    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self.client:
            await self.client.start()
            return
        if not self.gateway_url:
            return

        subscribe_url = self.gateway_url.rstrip("/") + "/events/subscribe"
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "topics": ["queues"],
                    "world_id": self.world_id or "",
                    "strategy_id": self.strategy_id or "",
                }
                resp = await client.post(subscribe_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    stream_url = data.get("stream_url")
                    token = data.get("token")
                    if stream_url:
                        try:
                            self.client = WebSocketClient(
                                stream_url, on_message=self.handle_message, token=token
                            )
                        except TypeError:
                            # Older or test clients may not accept a token parameter
                            self.client = WebSocketClient(
                                stream_url, on_message=self.handle_message
                            )
                        await self.client.start()
                        return
        except Exception:
            return

        if self.client:
            await self.client.start()
            return

        # No legacy watch fallback; WebSocket is required
    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
