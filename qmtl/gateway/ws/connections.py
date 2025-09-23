from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence, Set


@dataclass
class ConnectionFilters:
    """Filter constraints applied to a WebSocket client."""

    world_id: str | None = None
    strategy_id: str | None = None
    scopes: Set[str] | None = None

    def copy(self) -> "ConnectionFilters":
        return ConnectionFilters(
            world_id=self.world_id,
            strategy_id=self.strategy_id,
            scopes=set(self.scopes) if self.scopes is not None else None,
        )


@dataclass(frozen=True)
class RegisteredClient:
    websocket: Any
    filters: ConnectionFilters


class ConnectionRegistry:
    """Track connected WebSocket clients and their subscription metadata."""

    def __init__(self) -> None:
        self._clients: Set[Any] = set()
        self._topics: dict[Any, Optional[Set[str]]] = {}
        self._filters: dict[Any, ConnectionFilters] = {}
        self._known_topics: Set[str] = set()
        self._lock = asyncio.Lock()

    async def add(self, websocket: Any, *, topics: Optional[Set[str]] = None) -> None:
        async with self._lock:
            self._clients.add(websocket)
            self._topics[websocket] = set(topics) if topics is not None else None
            self._filters.setdefault(websocket, ConnectionFilters())

    async def remove(self, websocket: Any) -> bool:
        async with self._lock:
            removed = websocket in self._clients
            if removed:
                self._clients.discard(websocket)
                self._topics.pop(websocket, None)
                self._filters.pop(websocket, None)
            return removed

    async def remove_many(self, websockets: Iterable[Any]) -> list[Any]:
        removed: list[Any] = []
        async with self._lock:
            for websocket in websockets:
                if websocket in self._clients:
                    removed.append(websocket)
                    self._clients.discard(websocket)
                    self._topics.pop(websocket, None)
                    self._filters.pop(websocket, None)
        return removed

    async def update_topics(self, websocket: Any, topics: Optional[Set[str]]) -> None:
        async with self._lock:
            if websocket in self._clients:
                self._topics[websocket] = set(topics) if topics is not None else None

    async def update_filters(
        self,
        websocket: Any,
        *,
        world_id: str | None = None,
        strategy_id: str | None = None,
        scopes: Optional[Set[str]] = None,
    ) -> None:
        async with self._lock:
            if websocket in self._clients:
                filt = self._filters.setdefault(websocket, ConnectionFilters())
                if world_id is not None:
                    filt.world_id = world_id
                if strategy_id is not None:
                    filt.strategy_id = strategy_id
                if scopes is not None:
                    filt.scopes = set(scopes)

    async def clients_for_topic(self, topic: str | None) -> list[RegisteredClient]:
        async with self._lock:
            result: list[RegisteredClient] = []
            for ws in self._clients:
                topics = self._topics.get(ws)
                if topic is None or topics is None or topic in topics:
                    filters = self._filters.setdefault(ws, ConnectionFilters())
                    result.append(RegisteredClient(ws, filters.copy()))
            return result

    async def note_topic(self, topic: str) -> bool:
        async with self._lock:
            if topic in self._known_topics:
                return False
            self._known_topics.add(topic)
            return True

    async def topic_counts(self) -> dict[str, int]:
        async with self._lock:
            topics: Set[str] = set(self._known_topics)
            for tset in self._topics.values():
                if tset is not None:
                    topics.update(tset)
            counts: dict[str, int] = {}
            for topic in topics:
                count = 0
                for tset in self._topics.values():
                    if tset is None or (tset is not None and topic in tset):
                        count += 1
                counts[topic] = count
            return counts

    async def all_clients(self) -> Sequence[Any]:
        async with self._lock:
            return list(self._clients)

    async def clear(self) -> list[Any]:
        async with self._lock:
            clients = list(self._clients)
            self._clients.clear()
            self._topics.clear()
            self._filters.clear()
            return clients
