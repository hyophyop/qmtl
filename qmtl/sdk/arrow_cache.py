from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable

try:
    import pyarrow as pa
except Exception:  # pragma: no cover - optional dependency
    pa = None  # type: ignore

try:
    import ray
except Exception:  # pragma: no cover - optional dependency
    ray = None  # type: ignore

from . import runtime
from .cache_view import CacheView

ARROW_AVAILABLE = pa is not None
RAY_AVAILABLE = ray is not None

# Feature gate controlled via environment variable
ARROW_CACHE_ENABLED = ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1"


class _Slice:
    def __init__(self, period: int) -> None:
        self.period = period
        if not ARROW_AVAILABLE:
            raise RuntimeError("pyarrow is required for Arrow cache")
        import pickle

        self._pickle = pickle
        self.ts = pa.array([], pa.int64())
        self.vals = pa.array([], pa.binary())

    def append(self, timestamp: int, payload: Any) -> None:
        self.ts = pa.concat_arrays([self.ts, pa.array([timestamp], pa.int64())])
        buf = self._pickle.dumps(payload)
        self.vals = pa.concat_arrays([self.vals, pa.array([buf], pa.binary())])
        if len(self.ts) > self.period:
            start = len(self.ts) - self.period
            self.ts = self.ts.slice(start)
            self.vals = self.vals.slice(start)

    def latest(self) -> tuple[int, Any] | None:
        if len(self.ts) == 0:
            return None
        idx = len(self.ts) - 1
        ts = self.ts[idx].as_py()
        val = self._pickle.loads(self.vals[idx].as_py())
        return int(ts), val

    def get_list(self) -> list[tuple[int, Any]]:
        ts = self.ts.to_pylist()
        vals = [self._pickle.loads(x) for x in self.vals.to_pylist()]
        return [(int(t), v) for t, v in zip(ts, vals)]

    @property
    def table(self) -> pa.Table:
        return pa.table({"t": self.ts, "v": self.vals})

    def slice_table(self, start: int, end: int) -> pa.Table:
        start = max(0, start)
        end = min(len(self.ts), end)
        length = max(0, end - start)
        return pa.table({"t": self.ts.slice(start, length), "v": self.vals.slice(start, length)})

    @property
    def resident_bytes(self) -> int:
        # Approximate memory usage backed by Arrow buffers
        return int(self.ts.nbytes) + int(self.vals.nbytes)


class ArrowCacheView:
    def __init__(self, data: Dict[str, Dict[int, _Slice]], *, track_access: bool = False) -> None:
        self._data = data
        self._track_access = track_access
        self._access_log: list[tuple[str, int]] = []

    def __getitem__(self, key: str):
        mp = self._data[key]
        return _SecondLevelView(mp, self._track_access, self._access_log)

    def access_log(self) -> list[tuple[str, int]]:
        return list(self._access_log)


class _SecondLevelView:
    def __init__(self, data: Dict[int, _Slice], track_access: bool, log: list[tuple[str, int]]) -> None:
        self._data = data
        self._track_access = track_access
        self._log = log

    def __getitem__(self, key: int):
        if self._track_access:
            self._log.append(("?", key))  # upstream id not tracked here
        return _SliceView(self._data[key])


class _SliceView:
    def __init__(self, sl: _Slice) -> None:
        self._slice = sl

    def latest(self) -> tuple[int, Any] | None:
        return self._slice.latest()

    def table(self) -> pa.Table:
        return self._slice.table


class NodeCacheArrow:
    """Arrow based cache backend."""

    def __init__(self, period: int) -> None:
        if not ARROW_AVAILABLE:
            raise RuntimeError("pyarrow not installed")
        self.period = period
        self._slices: Dict[tuple[str, int], _Slice] = {}
        self._last_ts: Dict[tuple[str, int], int | None] = {}
        self._missing: Dict[tuple[str, int], bool] = {}
        self._filled: Dict[tuple[str, int], int] = {}
        self._last_seen: Dict[tuple[str, int], int] = {}

        self._evict_interval = int(os.getenv("QMTL_CACHE_EVICT_INTERVAL", "60"))
        if RAY_AVAILABLE and not runtime.NO_RAY:
            self._evictor = _Evictor.options(name=f"evictor_{id(self)}").remote(self._evict_interval)
            self_ref = self
            ray.get(self._evictor.start.remote(self_ref))
        else:
            self._start_thread_evictor()

    def _start_thread_evictor(self) -> None:
        import threading

        def loop() -> None:
            while True:
                time.sleep(self._evict_interval)
                self.evict_expired()

        t = threading.Thread(target=loop, daemon=True)
        t.start()

    # --------------------------------------------------------------
    def _ensure(self, u: str, interval: int) -> _Slice:
        key = (u, interval)
        if key not in self._slices:
            self._slices[key] = _Slice(self.period)
            self._last_ts[key] = None
            self._missing[key] = False
            self._filled[key] = 0
            self._last_seen[key] = 0
        return self._slices[key]

    def append(self, u: str, interval: int, timestamp: int, payload: Any) -> None:
        sl = self._ensure(u, interval)
        bucket = timestamp - (timestamp % interval)
        prev = self._last_ts.get((u, interval))
        if prev is None:
            self._missing[(u, interval)] = False
            self._last_ts[(u, interval)] = bucket
        else:
            if bucket < prev:
                # Late arrival: do not regress last_ts nor set missing
                self._missing[(u, interval)] = False
            else:
                self._missing[(u, interval)] = prev + interval != bucket
                self._last_ts[(u, interval)] = bucket
        sl.append(bucket, payload)
        filled = self._filled[(u, interval)]
        if filled < self.period:
            filled += 1
        self._filled[(u, interval)] = filled
        self._last_seen[(u, interval)] = bucket

    def ready(self) -> bool:
        if not self._slices:
            return False
        for key, count in self._filled.items():
            if count < self.period:
                return False
        return True

    def drop(self, u: str, interval: int) -> None:
        """Remove cached data for ``(u, interval)``."""
        key = (u, interval)
        self._slices.pop(key, None)
        self._last_ts.pop(key, None)
        self._missing.pop(key, None)
        self._filled.pop(key, None)
        self._last_seen.pop(key, None)

    def drop_upstream(self, upstream_id: str, interval: int) -> None:
        """Alias for :meth:`drop` removing cache for ``upstream_id``."""
        key = (upstream_id, interval)
        self._slices.pop(key, None)
        self._last_ts.pop(key, None)
        self._missing.pop(key, None)
        self._filled.pop(key, None)
        self._last_seen.pop(key, None)

    def view(self, *, track_access: bool = False) -> CacheView:
        """Return a CacheView-compatible structure for Arrow backend.

        Adapts Arrow slices to the standard CacheView contract by exposing
        ``list[(timestamp, value)]`` at the deepest level, enabling identical
        access patterns across backends.
        """
        data: Dict[str, Dict[int, list[tuple[int, Any]]]] = {}
        for (u, i), sl in self._slices.items():
            data.setdefault(u, {})[i] = sl.get_list()
        return CacheView(data, track_access=track_access)

    def missing_flags(self) -> Dict[str, Dict[int, bool]]:
        result: Dict[str, Dict[int, bool]] = {}
        for (u, i), flag in self._missing.items():
            result.setdefault(u, {})[i] = flag
        return result

    def last_timestamps(self) -> Dict[str, Dict[int, int | None]]:
        result: Dict[str, Dict[int, int | None]] = {}
        for (u, i), ts in self._last_ts.items():
            result.setdefault(u, {})[i] = ts
        return result

    def watermark(self, *, allowed_lateness: int = 0) -> int | None:
        """Return event-time watermark based on last timestamps.

        Watermark is ``min(last_ts) - allowed_lateness`` across all observed
        ``(upstream_id, interval)`` pairs. Returns ``None`` when empty.
        """
        last = [ts for ts in self._last_ts.values() if ts is not None]
        if not last:
            return None
        return int(min(last)) - int(allowed_lateness)

    def latest(self, u: str, interval: int) -> tuple[int, Any] | None:
        sl = self._slices.get((u, interval))
        if not sl:
            return None
        return sl.latest()

    @property
    def resident_bytes(self) -> int:
        total = 0
        for sl in self._slices.values():
            total += sl.resident_bytes
        return total

    def evict_expired(self) -> None:
        now = int(time.time())
        for key, last in list(self._last_seen.items()):
            u, i = key
            guard = self.period * i
            if last is not None and now - last > guard:
                self._slices.pop(key, None)
                self._last_ts.pop(key, None)
                self._missing.pop(key, None)
                self._filled.pop(key, None)
                self._last_seen.pop(key, None)


if RAY_AVAILABLE:

    @ray.remote
    class _Evictor:
        def __init__(self, interval: int) -> None:
            self._interval = interval

        def start(self, cache: NodeCacheArrow) -> None:
            while True:
                time.sleep(self._interval)
                cache.evict_expired()

else:

    class _Evictor:  # pragma: no cover - dummy placeholder
        pass
