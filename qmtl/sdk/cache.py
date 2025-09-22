from __future__ import annotations

import json
from typing import Any, Iterable

import numpy as np
import xarray as xr

from .cache_view import CacheView
from .backfill_state import BackfillState
from . import metrics as sdk_metrics
from . import hash_utils as default_hash_utils
from qmtl.common.compute_key import DEFAULT_EXECUTION_DOMAIN


class _RingBuffer:
    def __init__(self, period: int) -> None:
        self.period = period
        self.data = np.empty((period, 2), dtype=object)
        self.data[:] = None
        self.offset = 0
        self.filled = 0

    def append(self, timestamp: int, payload: Any) -> None:
        self.data[self.offset, 0] = timestamp
        self.data[self.offset, 1] = payload
        self.offset = (self.offset + 1) % self.period
        if self.filled < self.period:
            self.filled += 1

    def ordered(self) -> np.ndarray:
        if self.filled < self.period:
            return np.concatenate((self.data[self.filled :], self.data[: self.filled]))
        return np.concatenate((self.data[self.offset :], self.data[: self.offset]))

    def latest(self) -> tuple[int, Any] | None:
        if self.filled == 0:
            return None
        idx = (self.offset - 1) % self.period
        ts = self.data[idx, 0]
        if ts is None:
            return None
        return int(ts), self.data[idx, 1]


class NodeCache:
    """In-memory cache backed by per-pair ring buffers."""

    def __init__(self, period: int) -> None:
        self.period = period
        self._buffers: dict[tuple[str, int], _RingBuffer] = {}
        self._last_ts: dict[tuple[str, int], int | None] = {}
        self._missing: dict[tuple[str, int], bool] = {}
        self._filled: dict[tuple[str, int], int] = {}
        self._offset: dict[tuple[str, int], int] = {}
        self.backfill_state = BackfillState()
        self._active_compute_key: str | None = None
        self._active_world_id: str = ""
        self._active_execution_domain: str = DEFAULT_EXECUTION_DOMAIN
        self._active_as_of: Any | None = None
        self._active_partition: Any | None = None

    def _ordered_array(self, u: str, interval: int) -> np.ndarray:
        """Return internal array for ``(u, interval)`` ordered oldest->latest."""
        buf = self._buffers[(u, interval)]
        filled = self._filled.get((u, interval), 0)
        offset = self._offset.get((u, interval), 0)
        if filled < self.period:
            return np.concatenate((buf.data[filled:], buf.data[:filled]))
        return np.concatenate((buf.data[offset:], buf.data[:offset]))

    # ------------------------------------------------------------------
    def _ensure_buffer(self, u: str, interval: int) -> _RingBuffer:
        key = (u, interval)
        if key not in self._buffers:
            self._buffers[key] = _RingBuffer(self.period)
            self._last_ts[key] = None
            self._missing[key] = False
            self._filled[key] = 0
            self._offset[key] = 0
        return self._buffers[key]

    def _clear_all(self) -> None:
        self._buffers.clear()
        self._last_ts.clear()
        self._missing.clear()
        self._filled.clear()
        self._offset.clear()
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
        """Activate ``compute_key`` and clear data when the context changes."""

        key = compute_key or "__default__"
        world = str(world_id or "")
        domain = str(execution_domain or DEFAULT_EXECUTION_DOMAIN)
        as_of_val = as_of
        partition_val = partition
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
        had_data = bool(self._buffers)
        self._clear_all()
        self._active_compute_key = key
        self._active_world_id = world
        self._active_execution_domain = domain
        self._active_as_of = as_of_val
        self._active_partition = partition_val
        if had_data:
            sdk_metrics.observe_cross_context_cache_hit(
                node_id,
                world,
                domain,
                as_of=str(as_of_val) if as_of_val is not None else None,
                partition=str(partition_val) if partition_val is not None else None,
            )

    def append(self, u: str, interval: int, timestamp: int, payload: Any) -> None:
        """Insert ``payload`` with ``timestamp`` for ``(u, interval)``."""
        buf = self._ensure_buffer(u, interval)
        timestamp_bucket = timestamp - (timestamp % interval)
        prev = self._last_ts.get((u, interval))
        if prev is None:
            self._missing[(u, interval)] = False
            self._last_ts[(u, interval)] = timestamp_bucket
        else:
            if timestamp_bucket < prev:
                # Late arrival: do not regress last_ts nor set missing
                self._missing[(u, interval)] = False
            else:
                self._missing[(u, interval)] = prev + interval != timestamp_bucket
                self._last_ts[(u, interval)] = timestamp_bucket
        off = self._offset.get((u, interval), 0)
        buf.data[off, 0] = timestamp_bucket
        buf.data[off, 1] = payload
        off = (off + 1) % self.period
        self._offset[(u, interval)] = off
        buf.offset = off
        filled = self._filled.get((u, interval), 0)
        if filled < self.period:
            filled += 1
        self._filled[(u, interval)] = filled
        buf.filled = filled

    # ------------------------------------------------------------------
    def ready(self) -> bool:
        if not self._buffers:
            return False
        for count in self._filled.values():
            if count < self.period:
                return False
        return True

    def _snapshot(self) -> dict[str, dict[int, list[tuple[int, Any]]]]:
        """Return a deep copy of the cache contents.

        This helper exists primarily for tests and should not be relied on by
        strategy code. ``CacheView`` instances returned by :meth:`view` provide
        the recommended read-only access to the cache.
        """
        result: dict[str, dict[int, list[tuple[int, Any]]]] = {}
        for (u, i), buf in self._buffers.items():
            result.setdefault(u, {})[i] = [
                (int(t), v) for t, v in self._ordered_array(u, i) if t is not None
            ]
        return result

    def view(
        self,
        *,
        track_access: bool = False,
        artifact_plane: Any | None = None,
    ) -> CacheView:
        """Return a :class:`CacheView` over the current cache contents."""

        data: dict[str, dict[int, list[tuple[int, Any]]]] = {}
        for (u, i), buf in self._buffers.items():
            data.setdefault(u, {})[i] = [
                (int(t), v) for t, v in self._ordered_array(u, i) if t is not None
            ]
        return CacheView(data, track_access=track_access, artifact_plane=artifact_plane)

    def missing_flags(self) -> dict[str, dict[int, bool]]:
        """Return gap flags for all ``(u, interval)`` pairs."""
        result: dict[str, dict[int, bool]] = {}
        for (u, i), flag in self._missing.items():
            result.setdefault(u, {})[i] = flag
        return result

    def last_timestamps(self) -> dict[str, dict[int, int | None]]:
        """Return last timestamps for all ``(u, interval)`` pairs."""
        result: dict[str, dict[int, int | None]] = {}
        for (u, i), ts in self._last_ts.items():
            result.setdefault(u, {})[i] = ts
        return result

    def input_window_hash(self, *, hash_utils=default_hash_utils) -> str:
        """Return a stable hash of the current cache window.

        The hash covers all ``(upstream_id, interval)`` slices ordered by
        upstream and interval. It is suitable for commit-log de-duplication of
        node outputs.
        """

        ordered: list[tuple[str, int, list[tuple[int, Any]]]] = []
        for (u, i), buf in sorted(self._buffers.items()):
            items = [
                (int(t), v) for t, v in self._ordered_array(u, i) if t is not None
            ]
            ordered.append((u, i, items))
        blob = json.dumps(ordered, sort_keys=True, default=repr).encode()
        return hash_utils._sha256(blob)

    # ------------------------------------------------------------------
    def watermark(self, *, allowed_lateness: int = 0) -> int | None:
        """Return event-time watermark for the cache."""
        last = [ts for ts in self._last_ts.values() if ts is not None]
        if not last:
            return None
        return int(min(last)) - int(allowed_lateness)

    def as_xarray(self) -> xr.DataArray:
        """Return a read-only ``xarray`` view of the internal tensor."""
        u_vals = sorted({u for u, _ in self._buffers.keys()})
        i_vals = sorted({i for _, i in self._buffers.keys()})
        data = np.empty((len(u_vals), len(i_vals), self.period, 2), dtype=object)
        data[:] = None
        for u_idx, u in enumerate(u_vals):
            for i_idx, i in enumerate(i_vals):
                if (u, i) in self._buffers:
                    data[u_idx, i_idx] = self._ordered_array(u, i)
        da = xr.DataArray(
            data,
            dims=("u", "i", "p", "f"),
            coords={"u": u_vals, "i": i_vals, "p": list(range(self.period)), "f": ["t", "v"]},
        )
        da.data = da.data.view()
        da.data.setflags(write=False)
        return da

    @property
    def resident_bytes(self) -> int:
        """Return total memory used by cached arrays in bytes."""
        return sum(buf.data.nbytes for buf in self._buffers.values())

    # ------------------------------------------------------------------
    def drop(self, u: str, interval: int) -> None:
        """Remove cached data for ``(u, interval)``."""
        key = (u, interval)
        self._buffers.pop(key, None)
        self._last_ts.pop(key, None)
        self._missing.pop(key, None)
        self._filled.pop(key, None)
        self._offset.pop(key, None)
        self.backfill_state._ranges.pop(key, None)

    def drop_upstream(self, upstream_id: str, interval: int) -> None:
        """Alias for :meth:`drop` removing cache for ``upstream_id``."""
        key = (upstream_id, interval)
        self._buffers.pop(key, None)
        self._last_ts.pop(key, None)
        self._missing.pop(key, None)
        self._filled.pop(key, None)
        self._offset.pop(key, None)
        self.backfill_state._ranges.pop(key, None)

    # ------------------------------------------------------------------
    def latest(self, u: str, interval: int) -> tuple[int, Any] | None:
        """Return the most recent ``(timestamp, payload)`` for a pair."""
        buf = self._buffers.get((u, interval))
        if not buf:
            return None
        return buf.latest()

    def get_slice(
        self,
        u: str,
        interval: int,
        *,
        count: int | None = None,
        start: int | None = None,
        end: int | None = None,
    ):
        """Return a windowed slice for ``(u, interval)``."""

        buf = self._buffers.get((u, interval))
        if buf is None:
            if count is not None:
                return []
            return xr.DataArray(
                np.empty((0, 2), dtype=object),
                dims=("p", "f"),
                coords={"p": [], "f": ["t", "v"]},
            )

        filled = self._filled.get((u, interval), 0)
        off = self._offset.get((u, interval), 0)
        arr = buf.data

        if count is not None:
            if count <= 0:
                return []
            n = min(count, filled)
            if filled < self.period:
                data = arr[:filled]
            else:
                data = np.concatenate((arr[off:], arr[:off]))
            subset = data[-n:]
            return [(int(t), v) for t, v in subset if t is not None]

        ordered = self._ordered_array(u, interval)

        slice_start = start if start is not None else 0
        slice_end = end if end is not None else self.period

        slice_start = max(0, slice_start + self.period if slice_start < 0 else slice_start)
        slice_end = max(0, slice_end + self.period if slice_end < 0 else slice_end)
        slice_start = min(self.period, slice_start)
        slice_end = min(self.period, slice_end)

        da = xr.DataArray(
            ordered,
            dims=("p", "f"),
            coords={"p": list(range(self.period)), "f": ["t", "v"]},
        )
        return da.isel(p=slice(slice_start, slice_end))

    def backfill_bulk(
        self,
        u: str,
        interval: int,
        items: Iterable[tuple[int, Any]],
    ) -> None:
        """Merge historical ``items`` with existing cache contents.

        ``items`` must be ordered by timestamp in ascending order. Existing
        payloads are kept when timestamps collide so that live ``append()``
        calls that happen during a backfill take precedence.
        """

        self._ensure_buffer(u, interval)

        backfill_items: list[tuple[int, Any]] = []
        for ts, payload in items:
            bucket = ts - (ts % interval)
            backfill_items.append((bucket, payload))

        if backfill_items:
            ranges: list[tuple[int, int]] = []
            start_range = backfill_items[0][0]
            prev = start_range
            for ts, _ in backfill_items[1:]:
                if ts == prev + interval:
                    prev = ts
                else:
                    ranges.append((start_range, prev))
                    start_range = ts
                    prev = ts
            ranges.append((start_range, prev))
            self.backfill_state.mark_ranges(u, interval, ranges)

        # Capture latest data after collecting items so concurrent ``append``
        # operations are taken into account during the merge.
        arr = self._buffers[(u, interval)].data
        existing: dict[int, Any] = {int(t): v for t, v in arr if t is not None}

        ts_payload: dict[int, Any] = dict(existing)
        for ts, payload in backfill_items:
            ts_payload.setdefault(ts, payload)

        merged = sorted(ts_payload.items())[-self.period :]

        new_arr = np.empty((self.period, 2), dtype=object)
        new_arr[:] = None
        for idx, (ts, payload) in enumerate(merged):
            new_arr[idx % self.period, 0] = ts
            new_arr[idx % self.period, 1] = payload

        self._buffers[(u, interval)].data = new_arr
        filled = min(len(merged), self.period)
        self._filled[(u, interval)] = filled
        self._offset[(u, interval)] = len(merged) % self.period
        self._buffers[(u, interval)].filled = filled
        self._buffers[(u, interval)].offset = len(merged) % self.period

        prev_last = self._last_ts.get((u, interval))
        if merged:
            last_ts = merged[-1][0]
            if prev_last is None:
                self._missing[(u, interval)] = False
            elif last_ts != prev_last:
                self._missing[(u, interval)] = prev_last + interval != last_ts
            self._last_ts[(u, interval)] = last_ts

