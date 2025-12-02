"""Arrow-backed cache backend implementation."""
from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any, Dict

from qmtl.foundation.common.compute_key import DEFAULT_EXECUTION_DOMAIN

from ..backfill_state import BackfillState
from .. import configuration
from ..cache_context import ComputeContext as CacheComputeContext
from .dependencies import ARROW_AVAILABLE, ARROW_CACHE_ENABLED, pa
from .eviction import EvictionStrategy, create_default_eviction_strategy
from .instrumentation import CacheInstrumentation, NOOP_INSTRUMENTATION, default_instrumentation
from .slices import _Slice
from .view import ArrowCacheView


class NodeCacheArrow:
    """Arrow based cache backend."""

    def __init__(
        self,
        period: int,
        *,
        metrics: CacheInstrumentation | None = None,
        eviction_strategy: EvictionStrategy | None = None,
    ) -> None:
        if not ARROW_AVAILABLE or pa is None:
            raise RuntimeError("pyarrow not installed")
        self._pa: Any = pa
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
        self._active_as_of: Any | None = None
        self._active_partition: Any | None = None
        self._active_node_id: str | None = None

        self._metrics = metrics or default_instrumentation()

        cfg = configuration.get_runtime_config()
        interval = int(cfg.cache.cache_evict_interval) if cfg is not None else 60
        self._evict_interval = interval
        self._eviction = eviction_strategy or create_default_eviction_strategy(self._evict_interval)
        self._eviction.start(self)

    # --------------------------------------------------------------
    def close(self) -> None:
        """Stop background eviction workers."""
        self._eviction.stop()

    def __del__(self) -> None:  # pragma: no cover - cleanup
        try:
            self.close()
        except Exception:
            pass

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
        as_of: Any | None = None,
        partition: Any | None = None,
    ) -> None:
        """Activate ``compute_key`` and clear cache when context changes."""

        key = compute_key or "__default__"
        world = str(world_id or "")
        domain = str(execution_domain or DEFAULT_EXECUTION_DOMAIN)
        as_of_val = as_of
        partition_val = partition
        self._active_node_id = node_id
        if self._active_compute_key is None:
            self._active_compute_key = key
            self._active_world_id = world
            self._active_execution_domain = domain
            self._active_as_of = as_of_val
            self._active_partition = partition_val
            return
        if self._active_compute_key == key:
            self._active_world_id = world
            self._active_execution_domain = domain
            self._active_as_of = as_of_val
            self._active_partition = partition_val
            return
        had_data = bool(self._slices)
        self._clear_all()
        self._active_compute_key = key
        self._active_world_id = world
        self._active_execution_domain = domain
        self._active_as_of = as_of_val
        self._active_partition = partition_val
        if had_data:
            self._metrics.observe_cross_context_cache_hit(
                node_id,
                world,
                domain,
                as_of=str(as_of_val) if as_of_val is not None else None,
                partition=str(partition_val) if partition_val is not None else None,
            )

    def append(self, u: str, interval: int, timestamp: int, payload: Any) -> None:
        sl = self._ensure(u, interval)
        bucket = timestamp - (timestamp % interval)
        prev = self._last_ts.get((u, interval))
        if prev is None:
            self._missing[(u, interval)] = False
            self._last_ts[(u, interval)] = bucket
        else:
            if bucket < prev:
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
        for count in self._filled.values():
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
        self.drop(upstream_id, interval)

    def view(
        self,
        *,
        track_access: bool = False,
        artifact_plane: Any | None = None,
    ) -> ArrowCacheView:
        """Return an Arrow-native :class:`CacheView` implementation."""

        data: Dict[str, Dict[int, _Slice]] = {}
        for (u, i), sl in self._slices.items():
            data.setdefault(u, {})[i] = sl
        return ArrowCacheView(
            data,
            track_access=track_access,
            artifact_plane=artifact_plane,
            metrics=self._metrics,
        )

    @property
    def active_context(self) -> CacheComputeContext | None:
        """Return the currently active compute context, if any."""

        if self._active_compute_key is None:
            return None
        return CacheComputeContext(
            compute_key=self._active_compute_key,
            world_id=self._active_world_id,
            execution_domain=self._active_execution_domain,
            as_of=self._active_as_of,
            partition=self._active_partition,
        )

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
            import numpy as np
            import xarray as xr

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

        import numpy as np
        import xarray as xr

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

    def record_resident_bytes(self, node_id: str) -> int:
        """Record resident bytes using the configured instrumentation."""

        total = self.resident_bytes
        self._metrics.observe_resident_bytes(node_id, total)
        return total

    def backfill_bulk(
        self,
        u: str,
        interval: int,
        items: Iterable[tuple[int, Any]],
    ) -> None:
        sl = self._ensure(u, interval)
        existing = dict(sl.get_list())
        backfill_items = self._normalize_backfill_items(items, interval)

        if backfill_items:
            self._mark_backfill_ranges(u, interval, backfill_items)

        merged = self._merge_backfill(existing, backfill_items)
        self._store_backfill(sl, merged)
        self._update_backfill_tracking(u, interval, merged)

    def _normalize_backfill_items(
        self, items: Iterable[tuple[int, Any]], interval: int
    ) -> list[tuple[int, Any]]:
        normalized: list[tuple[int, Any]] = []
        for ts, payload in items:
            bucket = ts - (ts % interval)
            normalized.append((bucket, payload))
        return normalized

    def _mark_backfill_ranges(
        self, u: str, interval: int, backfill_items: list[tuple[int, Any]]
    ) -> None:
        ts_sorted = sorted({ts for ts, _ in backfill_items})
        if not ts_sorted:
            return

        ranges: list[tuple[int, int]] = []
        start_range = ts_sorted[0]
        prev = start_range
        for ts in ts_sorted[1:]:
            if ts == prev + interval:
                prev = ts
                continue
            ranges.append((start_range, prev))
            start_range = ts
            prev = ts
        ranges.append((start_range, prev))
        self.backfill_state.mark_ranges(u, interval, ranges)

    def _merge_backfill(
        self,
        existing: dict[int, Any],
        backfill_items: list[tuple[int, Any]],
    ) -> list[tuple[int, Any]]:
        merged_map: dict[int, Any] = dict(existing)
        for ts, payload in backfill_items:
            merged_map.setdefault(ts, payload)
        return sorted(merged_map.items())[-self.period :]

    def _store_backfill(self, sl: _Slice, merged: list[tuple[int, Any]]) -> None:
        if ARROW_AVAILABLE:
            import pickle

            ts_list = [int(t) for t, _ in merged]
            val_list = [pickle.dumps(v) for _, v in merged]
            sl.ts = self._pa.array(ts_list, self._pa.int64())
            sl.vals = self._pa.array(val_list, self._pa.binary())
            return

        # pragma: no cover - safety guard
        for ts, v in merged:
            sl.append(int(ts), v)

    def _update_backfill_tracking(
        self, u: str, interval: int, merged: list[tuple[int, Any]]
    ) -> None:
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

    def eviction_tick(self) -> None:
        """Manually trigger the eviction strategy loop."""

        self._eviction.tick()


__all__ = [
    "NodeCacheArrow",
    "ARROW_AVAILABLE",
    "ARROW_CACHE_ENABLED",
]
