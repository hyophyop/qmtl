from __future__ import annotations

import os
import time
import threading
from collections.abc import Iterable, Sequence
from typing import Any, Dict

try:
    import pyarrow as pa
except Exception:  # pragma: no cover - optional dependency
    pa = None  # type: ignore

try:
    import ray
except Exception:  # pragma: no cover - optional dependency
    ray = None  # type: ignore

from . import metrics as sdk_metrics, runtime
from .backfill_state import BackfillState
from qmtl.common.compute_key import DEFAULT_EXECUTION_DOMAIN

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
    """Hierarchical read-only view backed by Arrow ``_Slice`` objects."""

    def __init__(self, data: Dict[str, Dict[int, _Slice]], *, track_access: bool = False) -> None:
        self._data = data
        self._track_access = track_access
        self._access_log: list[tuple[str, int]] = []

    def __getitem__(self, key: Any):
        from .node import Node  # local import to avoid cycle

        if isinstance(key, Node):
            key = key.node_id
        mp = self._data[key]
        return _SecondLevelView(mp, key, self._track_access, self._access_log)

    def __getattr__(self, name: str):  # pragma: no cover - convenience
        if name in self._data:
            return self.__getitem__(name)
        raise AttributeError(name)

    def access_log(self) -> list[tuple[str, int]]:
        return list(self._access_log)


class _SecondLevelView:
    def __init__(self, data: Dict[int, _Slice], upstream: str, track_access: bool, log: list[tuple[str, int]]) -> None:
        self._data = data
        self._upstream = upstream
        self._track_access = track_access
        self._log = log

    def __getitem__(self, key: int):
        if self._track_access:
            self._log.append((self._upstream, key))
            sdk_metrics.observe_cache_read(self._upstream, key)
        return _SliceView(self._data[key])


class _SliceView(Sequence):
    def __init__(self, sl: _Slice, start: int = 0, end: int | None = None) -> None:
        self._slice = sl
        self._start = start
        self._end = len(sl.ts) if end is None else end

    def __len__(self) -> int:
        return self._end - self._start

    def __getitem__(self, idx: int | slice):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(len(self))
            if step != 1:
                return [self[i] for i in range(start, stop, step)]
            return _SliceView(self._slice, self._start + start, self._start + stop)
        if idx < 0:
            idx += len(self)
        if idx < 0 or idx >= len(self):
            raise IndexError("index out of range")
        real = self._start + idx
        ts = self._slice.ts[real].as_py()
        val = self._slice._pickle.loads(self._slice.vals[real].as_py())
        return int(ts), val

    def latest(self) -> tuple[int, Any] | None:
        return self[-1] if len(self) else None

    def table(self) -> pa.Table:
        return self._slice.slice_table(self._start, self._end)


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
        self.backfill_state = BackfillState()
        self._active_compute_key: str | None = None
        self._active_world_id: str = ""
        self._active_execution_domain: str = DEFAULT_EXECUTION_DOMAIN

        self._evict_interval = int(os.getenv("QMTL_CACHE_EVICT_INTERVAL", "60"))
        self._stop_event = threading.Event()
        self._evict_thread: threading.Thread | None = None
        self._evictor = None
        if RAY_AVAILABLE and not runtime.NO_RAY:
            self._evictor = _Evictor.options(name=f"evictor_{id(self)}").remote(self._evict_interval)
            self_ref = self
            self._evictor.start.remote(self_ref)
        else:
            self._start_thread_evictor()

    def _start_thread_evictor(self) -> None:
        def loop() -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(self._evict_interval)
                self.evict_expired()

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        self._evict_thread = t

    def close(self) -> None:
        """Stop background eviction workers."""
        self._stop_event.set()
        if self._evict_thread is not None:
            self._evict_thread.join(timeout=0)
        if RAY_AVAILABLE and not runtime.NO_RAY and self._evictor is not None:
            ray.get(self._evictor.stop.remote())

    def __del__(self) -> None:  # pragma: no cover - cleanup
        self.close()

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

    def _clear_all(self) -> None:
        self._slices.clear()
        self._last_ts.clear()
        self._missing.clear()
        self._filled.clear()
        self._last_seen.clear()
        self.backfill_state = BackfillState()

    def activate_compute_key(
        self,
        compute_key: str | None,
        *,
        node_id: str,
        world_id: str | None = None,
        execution_domain: str | None = None,
    ) -> None:
        """Activate ``compute_key`` and clear cache when context changes."""

        key = compute_key or "__default__"
        world = str(world_id or "")
        domain = str(execution_domain or DEFAULT_EXECUTION_DOMAIN)
        if self._active_compute_key is None:
            self._active_compute_key = key
            self._active_world_id = world
            self._active_execution_domain = domain
            return
        if self._active_compute_key == key:
            self._active_world_id = world
            self._active_execution_domain = domain
            return
        had_data = bool(self._slices)
        self._clear_all()
        self._active_compute_key = key
        self._active_world_id = world
        self._active_execution_domain = domain
        if had_data:
            sdk_metrics.observe_cross_context_cache_hit(node_id, world, domain)

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

    def view(self, *, track_access: bool = False) -> ArrowCacheView:
        """Return an Arrow-native :class:`CacheView` implementation."""

        data: Dict[str, Dict[int, _Slice]] = {}
        for (u, i), sl in self._slices.items():
            data.setdefault(u, {})[i] = sl
        return ArrowCacheView(data, track_access=track_access)

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

    def get_slice(
        self,
        u: str,
        interval: int,
        *,
        count: int | None = None,
        start: int | None = None,
        end: int | None = None,
    ):
        sl = self._slices.get((u, interval))
        if sl is None:
            if count is not None:
                return []
            import numpy as np  # type: ignore
            import xarray as xr  # type: ignore

            return xr.DataArray(
                np.empty((0, 2), dtype=object),
                dims=("p", "f"),
                coords={"p": [], "f": ["t", "v"]},
            )

        items = sl.get_list()
        if count is not None:
            if count <= 0:
                return []
            return items[-min(count, len(items)) :]

        # Build DataArray like NodeCache.get_slice for consistency
        import numpy as np  # type: ignore
        import xarray as xr  # type: ignore

        arr = np.empty((self.period, 2), dtype=object)
        arr[:] = None
        for idx, (ts, val) in enumerate(items[-self.period :]):
            arr[idx, 0] = ts
            arr[idx, 1] = val

        slice_start = start if start is not None else 0
        slice_end = end if end is not None else self.period
        slice_start = max(0, slice_start + self.period if slice_start < 0 else slice_start)
        slice_end = max(0, slice_end + self.period if slice_end < 0 else slice_end)
        slice_start = min(self.period, slice_start)
        slice_end = min(self.period, slice_end)

        da = xr.DataArray(
            arr,
            dims=("p", "f"),
            coords={"p": list(range(self.period)), "f": ["t", "v"]},
        )
        return da.isel(p=slice(slice_start, slice_end))

    @property
    def resident_bytes(self) -> int:
        total = 0
        for sl in self._slices.values():
            total += sl.resident_bytes
        return total

    # Compatibility helpers to mirror NodeCache API used in tests/backfill
    def backfill_bulk(
        self,
        u: str,
        interval: int,
        items: Iterable[tuple[int, Any]],
    ) -> None:
        sl = self._ensure(u, interval)
        # Build merged mapping with live data taking precedence
        existing: dict[int, Any] = {ts: v for ts, v in sl.get_list()}
        backfill_items: list[tuple[int, Any]] = []
        for ts, payload in items:
            bucket = ts - (ts % interval)
            backfill_items.append((bucket, payload))

        # Record contiguous ranges for observability/merging behaviour
        if backfill_items:
            # De-duplicate by timestamp only; payload equality does not matter for ranges
            ts_sorted = sorted({ts for ts, _ in backfill_items})
            ranges: list[tuple[int, int]] = []
            start_range = ts_sorted[0]
            prev = start_range
            for ts in ts_sorted[1:]:
                if ts == prev + interval:
                    prev = ts
                else:
                    ranges.append((start_range, prev))
                    start_range = ts
                    prev = ts
            ranges.append((start_range, prev))
            self.backfill_state.mark_ranges(u, interval, ranges)

        merged_map: dict[int, Any] = dict(existing)
        for ts, payload in backfill_items:
            merged_map.setdefault(ts, payload)
        merged = sorted(merged_map.items())[-self.period :]

        # Rewrite slice arrays
        if ARROW_AVAILABLE:
            import pyarrow as pa  # type: ignore
            import pickle

            ts_list = [int(t) for t, _ in merged]
            val_list = [pickle.dumps(v) for _, v in merged]
            sl.ts = pa.array(ts_list, pa.int64())
            sl.vals = pa.array(val_list, pa.binary())
        else:  # pragma: no cover - safety guard
            for ts, v in merged:
                sl.append(int(ts), v)

        # Update bookkeeping similar to append()
        self._filled[(u, interval)] = min(len(merged), self.period)
        last_ts = merged[-1][0] if merged else None
        prev_last = self._last_ts.get((u, interval))
        if last_ts is not None:
            if prev_last is None:
                self._missing[(u, interval)] = False
            elif last_ts != prev_last:
                self._missing[(u, interval)] = prev_last + interval != last_ts
            self._last_ts[(u, interval)] = last_ts
        self._last_seen[(u, interval)] = last_ts or 0

    def _snapshot(self) -> Dict[str, Dict[int, list[tuple[int, Any]]]]:
        result: Dict[str, Dict[int, list[tuple[int, Any]]]] = {}
        for (u, i), sl in self._slices.items():
            result.setdefault(u, {})[i] = sl.get_list()
        return result

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
            self._stop_event = threading.Event()

        def start(self, cache: NodeCacheArrow) -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(self._interval)
                cache.evict_expired()

        def stop(self) -> None:
            self._stop_event.set()

else:

    class _Evictor:  # pragma: no cover - dummy placeholder
        pass
