from __future__ import annotations

import httpx
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from .ws_client import WebSocketClient

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .node import TagQueryNode


class TagQueryManager:
    """Manage :class:`TagQueryNode` instances and deliver updates."""

    def __init__(
        self,
        gateway_url: str | None = None,
        *,
        ws_client: WebSocketClient | None = None,
    ) -> None:
        self.gateway_url = gateway_url
        if ws_client is not None:
            ws_client.on_message = self.handle_message
            self.client = ws_client
        elif gateway_url:
            self.client = WebSocketClient(
                gateway_url.rstrip("/") + "/ws",
                on_message=self.handle_message,
            )
        else:
            self.client = None
        self._nodes: Dict[Tuple[Tuple[str, ...], int, str], List[TagQueryNode]] = {}

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
                    "match_mode": match_mode,
                }
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    queues = resp.json().get("queues", [])
                except httpx.RequestError:
                    queues = []
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
            queues = payload.get("queues", [])
            match_mode = payload.get("match_mode", "any")
            if isinstance(tags, str):
                tags = [t for t in tags.split(",") if t]
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

    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
