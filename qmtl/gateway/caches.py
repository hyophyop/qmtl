"""Reusable cache primitives for the Gateway WorldService proxy."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Dict, Generic, Mapping, MutableMapping, Optional, TypeVar

T = TypeVar("T")


@dataclass
class TTLCacheEntry(Generic[T]):
    """Container storing cached values with an absolute expiry."""

    value: T
    expires_at: float

    def is_valid(self, now: float) -> bool:
        return now < self.expires_at


@dataclass(frozen=True)
class TTLCacheResult(Generic[T]):
    """Result of a TTL cache lookup."""

    value: Optional[T]
    present: bool
    fresh: bool

    @property
    def stale(self) -> bool:
        return self.present and not self.fresh


class TTLCache(Generic[T]):
    """Time-based cache with optional stale reads."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        store: Optional[MutableMapping[str, TTLCacheEntry[T]]] = None,
    ) -> None:
        self._clock = clock
        self._store = store if store is not None else {}

    def lookup(self, key: str) -> TTLCacheResult[T]:
        """Retrieve a cached value and whether it is still valid."""

        entry = self._store.get(key)
        if entry is None:
            return TTLCacheResult(value=None, present=False, fresh=False)
        fresh = entry.is_valid(self._clock())
        return TTLCacheResult(value=entry.value, present=True, fresh=fresh)

    def set(self, key: str, value: T, ttl: float) -> None:
        self._store[key] = TTLCacheEntry(value=value, expires_at=self._clock() + ttl)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def expire(self, key: str) -> None:
        """Force a cached value to become stale while retaining the payload."""

        entry = self._store.get(key)
        if entry is not None:
            entry.expires_at = self._clock() - 1

    def clear(self) -> None:
        self._store.clear()


@dataclass
class ActivationCacheEntry(Generic[T]):
    """Conditional request payload keyed by an ETag."""

    etag: str
    payload: T


class ActivationCache(Generic[T]):
    """Stores activation payloads indexed by composite identifiers."""

    def __init__(self) -> None:
        self._store: Dict[str, ActivationCacheEntry[T]] = {}

    def get(self, key: str) -> Optional[ActivationCacheEntry[T]]:
        return self._store.get(key)

    def conditional_headers(
        self, key: str, headers: Optional[Mapping[str, str]] = None
    ) -> Dict[str, str]:
        result: Dict[str, str] = dict(headers or {})
        entry = self._store.get(key)
        if entry and entry.etag:
            result["If-None-Match"] = entry.etag
        return result

    def set(self, key: str, etag: str, payload: T) -> None:
        self._store[key] = ActivationCacheEntry(etag=etag, payload=payload)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


__all__ = [
    "ActivationCache",
    "ActivationCacheEntry",
    "TTLCache",
    "TTLCacheResult",
    "TTLCacheEntry",
]
