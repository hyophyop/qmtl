"""Lightweight in-memory LRU cache with TTL support."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Generic, Iterator, TypeVar


K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class _Entry(Generic[V]):
    value: V
    expires_at: float
    weight: int


class LRUCache(Generic[K, V]):
    """Simple ordered LRU cache with millisecond TTL semantics."""

    def __init__(
        self,
        *,
        max_entries: int,
        ttl_ms: int,
        clock: Callable[[], float],
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._data: "OrderedDict[K, _Entry[V]]" = OrderedDict()
        self._max_entries = int(max_entries)
        self._ttl_seconds = max(0.0, float(ttl_ms) / 1000.0)
        self._clock = clock
        self._resident_bytes = 0

    # ------------------------------------------------------------------
    def _now(self) -> float:
        return float(self._clock())

    def _ttl_expires_at(self, now: float) -> float:
        if self._ttl_seconds == 0:
            return float("inf")
        return now + self._ttl_seconds

    def _evict_one(self) -> None:
        key, entry = self._data.popitem(last=False)
        self._resident_bytes -= max(0, entry.weight)

    def _prune_expired(self, now: float | None = None) -> None:
        if not self._data:
            return
        ts = self._now() if now is None else now
        stale: list[K] = []
        for key, entry in self._data.items():
            if entry.expires_at <= ts:
                stale.append(key)
        for key in stale:
            entry = self._data.pop(key, None)
            if entry is not None:
                self._resident_bytes -= max(0, entry.weight)

    # ------------------------------------------------------------------
    def get(self, key: K) -> V | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        now = self._now()
        if entry.expires_at <= now:
            self._data.pop(key, None)
            self._resident_bytes -= max(0, entry.weight)
            return None
        self._data.move_to_end(key)
        return entry.value

    def set(self, key: K, value: V, *, weight: int = 0) -> None:
        now = self._now()
        expires_at = self._ttl_expires_at(now)
        weight = max(0, int(weight))
        if key in self._data:
            previous = self._data.pop(key)
            self._resident_bytes -= max(0, previous.weight)
        self._data[key] = _Entry(value=value, expires_at=expires_at, weight=weight)
        self._data.move_to_end(key)
        self._resident_bytes += weight
        self._prune_expired(now)
        while len(self._data) > self._max_entries:
            self._evict_one()

    def pop(self, key: K) -> V | None:
        entry = self._data.pop(key, None)
        if entry is None:
            return None
        self._resident_bytes -= max(0, entry.weight)
        return entry.value

    def clear(self) -> None:
        self._data.clear()
        self._resident_bytes = 0

    def prune(self) -> None:
        self._prune_expired()

    # ------------------------------------------------------------------
    @property
    def resident_bytes(self) -> int:
        return max(0, self._resident_bytes)

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[K]:
        return iter(self._data)


__all__ = ["LRUCache"]

