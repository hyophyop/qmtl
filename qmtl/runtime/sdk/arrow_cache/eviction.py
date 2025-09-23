"""Eviction strategies for the Arrow cache backend."""
from __future__ import annotations

import threading
from typing import Protocol

from .dependencies import RAY_AVAILABLE, ray


class EvictableCache(Protocol):
    def evict_expired(self) -> None: ...


class EvictionStrategy(Protocol):
    def start(self, cache: EvictableCache) -> None: ...

    def tick(self) -> None: ...

    def stop(self) -> None: ...


class ThreadedEvictionStrategy:
    """Simple eviction runner backed by a background thread."""

    def __init__(self, interval: int) -> None:
        self._interval = interval
        self._cache: EvictableCache | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, cache: EvictableCache) -> None:
        self._cache = cache
        if self._thread is not None:
            return
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()
        self._thread = thread

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            self.tick()

    def tick(self) -> None:
        cache = self._cache
        if cache is not None:
            cache.evict_expired()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=0)
        self._thread = None
        self._cache = None
        self._stop_event = threading.Event()


if RAY_AVAILABLE:

    @ray.remote  # type: ignore[misc]
    class _RayEvictor:
        def __init__(self, interval: int) -> None:
            self._interval = interval
            self._stop_event = threading.Event()

        def start(self, cache: EvictableCache) -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(self._interval)
                cache.evict_expired()

        def stop(self) -> None:
            self._stop_event.set()
else:  # pragma: no cover - optional dependency shim

    class _RayEvictor:  # type: ignore[too-many-ancestors]
        pass


class RayEvictionStrategy:
    """Eviction strategy backed by a Ray actor."""

    def __init__(self, interval: int) -> None:
        self._interval = interval
        self._actor = None
        self._cache: EvictableCache | None = None

    def start(self, cache: EvictableCache) -> None:
        if not RAY_AVAILABLE or ray is None:
            raise RuntimeError("ray is not available")
        self._cache = cache
        self._actor = _RayEvictor.options(name=f"evictor_{id(cache)}").remote(self._interval)
        self._actor.start.remote(cache)

    def tick(self) -> None:
        cache = self._cache
        if cache is not None:
            cache.evict_expired()

    def stop(self) -> None:
        if self._actor is not None and ray is not None:
            try:
                ray.get(self._actor.stop.remote())
            finally:
                self._actor = None
        self._cache = None


def create_default_eviction_strategy(interval: int) -> EvictionStrategy:
    """Return the default eviction strategy for the current runtime."""

    from .. import runtime

    if RAY_AVAILABLE and ray is not None and not runtime.NO_RAY:
        return RayEvictionStrategy(interval)
    return ThreadedEvictionStrategy(interval)


__all__ = [
    "EvictionStrategy",
    "ThreadedEvictionStrategy",
    "RayEvictionStrategy",
    "create_default_eviction_strategy",
]
