from __future__ import annotations

from typing import Any, Dict, List
import asyncio


class InMemoryRedis:
    """Minimal in-memory Redis clone used when no ``redis_dsn`` is configured."""

    def __init__(self) -> None:
        self._values: Dict[str, Any] = {}
        self._lists: Dict[str, List[Any]] = {}
        self._lock = asyncio.Lock()

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Any:
        async with self._lock:
            return self._values.get(key)

    async def set(self, key: str, value: Any, *args: Any, **kwargs: Any) -> bool:
        async with self._lock:
            self._values[key] = value
        return True

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
            lst = self._lists.get(name)
            if lst:
                return lst.pop(0)
            return None

    async def flushall(self) -> None:
        async with self._lock:
            self._values.clear()
            self._lists.clear()


__all__ = ["InMemoryRedis"]
