from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncGenerator, DefaultDict, List


class QueueWatchHub:
    """Manage subscribers for tag query updates."""

    def __init__(self) -> None:
        self._subs: DefaultDict[str, List[asyncio.Queue[List[str]]]] = defaultdict(list)
        self._latest: DefaultDict[str, List[str]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def _key(self, tags: List[str], interval: int) -> str:
        return f"{','.join(sorted(tags))}:{interval}"

    async def subscribe(self, tags: List[str], interval: int) -> AsyncGenerator[List[str], None]:
        q: asyncio.Queue[List[str]] = asyncio.Queue()
        key = self._key(tags, interval)
        async with self._lock:
            self._subs[key].append(q)
            initial = list(self._latest.get(key, []))
        if initial:
            await q.put(initial)
        try:
            while True:
                data = await q.get()
                yield data
        finally:
            async with self._lock:
                self._subs[key].remove(q)

    async def broadcast(self, tags: List[str], interval: int, queues: List[str]) -> None:
        key = self._key(tags, interval)
        async with self._lock:
            if self._latest.get(key, []) == list(queues):
                return
            targets = list(self._subs.get(key, []))
            self._latest[key] = list(queues)
        for q in targets:
            await q.put(list(queues))


__all__ = ["QueueWatchHub"]
