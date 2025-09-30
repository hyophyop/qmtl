from __future__ import annotations

from typing import Any, Dict, List
import asyncio
import time


class InMemoryRedis:
    """Minimal in-memory Redis clone used when no ``redis_dsn`` is configured."""

    def __init__(self) -> None:
        self._values: Dict[str, Any] = {}
        self._lists: Dict[str, List[Any]] = {}
        self._lock = asyncio.Lock()
        self._expiry: Dict[str, float] = {}

    def _purge_if_expired(self, key: str) -> None:
        expires_at = self._expiry.get(key)
        if expires_at is None:
            return
        if expires_at <= time.monotonic():
            self._values.pop(key, None)
            self._lists.pop(key, None)
            self._expiry.pop(key, None)

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Any:
        async with self._lock:
            self._purge_if_expired(key)
            return self._values.get(key)

    async def set(self, key: str, value: Any, *args: Any, **kwargs: Any) -> bool:
        async with self._lock:
            nx = kwargs.get("nx", False)
            px = kwargs.get("px")
            ex = kwargs.get("ex")
            self._purge_if_expired(key)
            if nx and key in self._values:
                return False
            self._values[key] = value
            ttl = None
            if px is not None:
                ttl = float(px) / 1000.0
            elif ex is not None:
                ttl = float(ex)
            if ttl is not None:
                self._expiry[key] = time.monotonic() + ttl
            elif key in self._expiry:
                self._expiry.pop(key, None)
        return True

    async def delete(self, *keys: str) -> int:
        async with self._lock:
            removed = 0
            for key in keys:
                self._purge_if_expired(key)
                if key in self._values:
                    del self._values[key]
                    removed += 1
                if key in self._lists:
                    del self._lists[key]
                    removed += 1
                if key in self._expiry:
                    del self._expiry[key]
            return removed

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: Any | None = None,
        mapping: Dict[str, Any] | None = None,
    ) -> int:
        async with self._lock:
            d = self._values.setdefault(name, {})
            if not isinstance(d, dict):
                d = {}
                self._values[name] = d
            if mapping is not None:
                d.update(mapping)
            elif key is not None:
                d[key] = value
        return 1

    async def hget(self, name: str, key: str) -> Any:
        async with self._lock:
            d = self._values.get(name)
            if isinstance(d, dict):
                return d.get(key)
            return None

    async def rpush(self, name: str, *values: Any) -> int:
        async with self._lock:
            lst = self._lists.setdefault(name, [])
            lst.extend(values)
            return len(lst)

    async def lpop(self, name: str) -> Any:
        async with self._lock:
            self._purge_if_expired(name)
            lst = self._lists.get(name)
            if lst:
                return lst.pop(0)
            return None

    async def lindex(self, name: str, index: int) -> Any:
        async with self._lock:
            self._purge_if_expired(name)
            lst = self._lists.get(name)
            if not lst:
                return None
            try:
                return lst[index]
            except IndexError:
                return None

    async def flushall(self) -> None:
        async with self._lock:
            self._values.clear()
            self._lists.clear()
            self._expiry.clear()


__all__ = ["InMemoryRedis"]
