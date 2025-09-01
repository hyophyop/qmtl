from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncGenerator, DefaultDict, List, Dict, Any

from qmtl.sdk.node import MatchMode


class QueueWatchHub:
    """Manage subscribers for tag query updates."""

    def __init__(self) -> None:
        self._subs: DefaultDict[str, List[asyncio.Queue[List[Dict[str, Any]]]]] = defaultdict(list)
        self._latest: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def _key(self, tags: List[str], interval: int, match_mode: MatchMode) -> str:
        return f"{','.join(sorted(tags))}:{interval}:{match_mode.value}"

    async def subscribe(
        self, tags: List[str], interval: int, match_mode: MatchMode
    ) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """Subscribe to queue updates for ``tags``.

        Parameters
        ----------
        tags:
            Tags to watch.
        interval:
            Bar interval.
        match_mode:
            Tag matching mode, either ``MatchMode.ANY`` or ``MatchMode.ALL``.
        """
        q: asyncio.Queue[List[Dict[str, Any]]] = asyncio.Queue()
        key = self._key(tags, interval, match_mode)
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

    async def broadcast(
        self,
        tags: List[str],
        interval: int,
        queues: List[Dict[str, Any]],
        match_mode: MatchMode,
    ) -> None:
        """Broadcast updated ``queues`` to subscribers.

        ``match_mode`` must be ``MatchMode.ANY`` or ``MatchMode.ALL``.
        """
        key = self._key(tags, interval, match_mode)
        async with self._lock:
            if self._latest.get(key, []) == list(queues):
                return
            targets = list(self._subs.get(key, []))
            self._latest[key] = list(queues)
        for q in targets:
            await q.put(list(queues))


__all__ = ["QueueWatchHub"]
