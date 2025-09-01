from __future__ import annotations

import asyncio
import json
import contextlib
import httpx
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

from .node import MatchMode

from .ws_client import WebSocketClient

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .node import TagQueryNode


class TagQueryManager:
    """Manage :class:`TagQueryNode` instances and deliver updates.

    Queue updates are received via the ControlBus-backed WebSocket from
    ``/events/subscribe``. The ``/queues/watch`` stream is retained only as a
    legacy fallback.
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
        self._watch_tasks: Dict[
            Tuple[Tuple[str, ...], int, MatchMode], asyncio.Task
        ] = {}
        self._use_watch = False

    # ------------------------------------------------------------------
    def register(self, node: TagQueryNode) -> None:
        key = (tuple(sorted(node.query_tags)), node.interval, node.match_mode)
        self._nodes.setdefault(key, []).append(node)
        if self._use_watch and key not in self._watch_tasks:
            self._watch_tasks[key] = asyncio.create_task(self._watch(*key))

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
            try:
                match_mode = MatchMode(payload.get("match_mode", "any"))
            except ValueError:
                return
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
                        self.client = WebSocketClient(
                            stream_url, on_message=self.handle_message, token=token
                        )
                        await self.client.start()
                        return
        except Exception:
            pass

        if self.client:
            await self.client.start()
            return

        # fallback to /queues/watch + HTTP reconcile
        self._use_watch = True
        await self.resolve_tags()
        for key in list(self._nodes.keys()):
            if key not in self._watch_tasks:
                self._watch_tasks[key] = asyncio.create_task(self._watch(*key))

    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
        for task in list(self._watch_tasks.values()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._watch_tasks.clear()

    async def _watch(
        self, tags: Tuple[str, ...], interval: int, match_mode: MatchMode
    ) -> None:
        if not self.gateway_url:
            return

        key = (tags, interval, match_mode)
        params = {
            "tags": ",".join(tags),
            "interval": interval,
            "match_mode": match_mode.value,
        }
        url = self.gateway_url.rstrip("/") + "/queues/watch"
        backoff: float = 1.0
        try:
            while key in self._nodes:
                try:
                    async with httpx.AsyncClient() as client:
                        async with client.stream("GET", url, params=params) as resp:
                            async for line in resp.aiter_lines():
                                if not line:
                                    continue
                                try:
                                    data = json.loads(line)
                                except json.JSONDecodeError:
                                    continue
                                payload = {
                                    "tags": list(tags),
                                    "interval": interval,
                                    "queues": data.get("queues", []),
                                    "match_mode": match_mode.value,
                                }
                                await self.handle_message(
                                    {"event": "queue_update", "data": payload}
                                )
                    backoff = 1.0
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                await asyncio.sleep(backoff)
        finally:
            self._watch_tasks.pop(key, None)
