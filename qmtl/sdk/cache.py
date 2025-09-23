from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

import numpy as np
import xarray as xr

from . import hash_utils as default_hash_utils
from . import metrics as sdk_metrics
from .backfill_state import BackfillState
from .cache_backfill import BackfillMerger
from .cache_context import ContextSwitchStrategy, ComputeContext
from .cache_reader import CacheWindowReader
from .cache_ring_buffer import RingBuffer
from .cache_view import CacheView
from qmtl.common.compute_key import DEFAULT_EXECUTION_DOMAIN

RingBufferFactory = Callable[[int], RingBuffer]
ReaderFactory = Callable[[Mapping[tuple[str, int], RingBuffer], int], CacheWindowReader]


class NodeCache:
    """In-memory cache backed by per-pair ring buffers."""

    def __init__(
        self,
        period: int,
        *,
        metrics: Any = sdk_metrics,
        context_strategy: ContextSwitchStrategy | None = None,
        backfill_merger: BackfillMerger | None = None,
        ring_buffer_factory: RingBufferFactory | None = None,
        reader_factory: ReaderFactory | None = None,
    ) -> None:
        self.period = period
        self._buffers: dict[tuple[str, int], RingBuffer] = {}
        self._last_ts: dict[tuple[str, int], int | None] = {}
        self._missing: dict[tuple[str, int], bool] = {}
        self.backfill_state = BackfillState()

        self._context_strategy = context_strategy or ContextSwitchStrategy(metrics)
        self._backfill_merger = backfill_merger or BackfillMerger(period)
        self._ring_buffer_factory = ring_buffer_factory or RingBuffer
        self._reader_factory: ReaderFactory = reader_factory or (
            lambda buffers, period: CacheWindowReader(buffers, period=period)
        )

        self._active_compute_key: str | None = None
        self._active_world_id: str = ""
        self._active_execution_domain: str = DEFAULT_EXECUTION_DOMAIN
        self._active_as_of: Any | None = None
        self._active_partition: Any | None = None

    @property
    def active_context(self) -> ComputeContext | None:
        return self._context_strategy.active

    def _ensure_buffer(self, upstream_id: str, interval: int) -> RingBuffer:
        key = (upstream_id, interval)
        if key not in self._buffers:
            self._buffers[key] = self._ring_buffer_factory(self.period)
            self._last_ts[key] = None
            self._missing[key] = False
        return self._buffers[key]

    def _clear_all(self) -> None:
        self._buffers.clear()
        self._last_ts.clear()
        self._missing.clear()
        self.backfill_state = BackfillState()

    # ------------------------------------------------------------------
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

        context, cleared = self._context_strategy.ensure(
            compute_key,
            node_id=node_id,
            world_id=world_id,
            execution_domain=execution_domain,
            as_of=as_of,
            partition=partition,
            had_data=bool(self._buffers),
        )
        self._active_compute_key = context.compute_key
        self._active_world_id = context.world_id
        self._active_execution_domain = context.execution_domain
        self._active_as_of = context.as_of
        self._active_partition = context.partition
        if cleared:
            self._clear_all()

    def append(self, upstream_id: str, interval: int, timestamp: int, payload: Any) -> None:
        """Insert ``payload`` with ``timestamp`` for ``(upstream_id, interval)``."""

        buffer = self._ensure_buffer(upstream_id, interval)
        timestamp_bucket = timestamp - (timestamp % interval)
        key = (upstream_id, interval)
        prev = self._last_ts.get(key)
        if prev is None:
            self._missing[key] = False
            self._last_ts[key] = timestamp_bucket
        else:
            if timestamp_bucket < prev:
                self._missing[key] = False
            else:
                self._missing[key] = prev + interval != timestamp_bucket
                self._last_ts[key] = timestamp_bucket
        buffer.append(timestamp_bucket, payload)

    # ------------------------------------------------------------------
    def ready(self) -> bool:
        if not self._buffers:
            return False
        for buffer in self._buffers.values():
            if buffer.filled < self.period:
                return False
        return True

    def _reader(self) -> CacheWindowReader:
        return self._reader_factory(self._buffers, self.period)

    def _snapshot(self) -> dict[str, dict[int, list[tuple[int, Any]]]]:
        """Return a deep copy of the cache contents (for tests)."""

        return self._reader().snapshot()

    def view(
        self,
        *,
        track_access: bool = False,
        artifact_plane: Any | None = None,
    ) -> CacheView:
        """Return a :class:`CacheView` over the current cache contents."""

        data = self._reader().view_data()
        return CacheView(data, track_access=track_access, artifact_plane=artifact_plane)

    def missing_flags(self) -> dict[str, dict[int, bool]]:
        """Return gap flags for all ``(upstream_id, interval)`` pairs."""

        result: dict[str, dict[int, bool]] = {}
        for (upstream, interval), flag in self._missing.items():
            result.setdefault(upstream, {})[interval] = flag
        return result

    def last_timestamps(self) -> dict[str, dict[int, int | None]]:
        """Return last timestamps for all ``(upstream_id, interval)`` pairs."""

        result: dict[str, dict[int, int | None]] = {}
        for (upstream, interval), ts in self._last_ts.items():
            result.setdefault(upstream, {})[interval] = ts
        return result

    def input_window_hash(self, *, hash_utils=default_hash_utils) -> str:
        """Return a stable hash of the current cache window."""

        return self._reader().input_window_hash(hash_utils=hash_utils)

    # ------------------------------------------------------------------
    def watermark(self, *, allowed_lateness: int = 0) -> int | None:
        """Return event-time watermark for the cache."""

        last = [ts for ts in self._last_ts.values() if ts is not None]
        if not last:
            return None
        return int(min(last)) - int(allowed_lateness)

    def as_xarray(self) -> xr.DataArray:
        """Return a read-only ``xarray`` view of the internal tensor."""

        return self._reader().as_xarray()

    @property
    def resident_bytes(self) -> int:
        """Return total memory used by cached arrays in bytes."""

        return sum(buffer.nbytes for buffer in self._buffers.values())

    # ------------------------------------------------------------------
    def drop(self, upstream_id: str, interval: int) -> None:
        """Remove cached data for ``(upstream_id, interval)``."""

        key = (upstream_id, interval)
        self._buffers.pop(key, None)
        self._last_ts.pop(key, None)
        self._missing.pop(key, None)
        self.backfill_state._ranges.pop(key, None)

    def drop_upstream(self, upstream_id: str, interval: int) -> None:
        """Alias for :meth:`drop` removing cache for ``upstream_id``."""

        self.drop(upstream_id, interval)

    # ------------------------------------------------------------------
    def latest(self, upstream_id: str, interval: int) -> tuple[int, Any] | None:
        """Return the most recent ``(timestamp, payload)`` for a pair."""

        buffer = self._buffers.get((upstream_id, interval))
        if buffer is None:
            return None
        return buffer.latest()

    def get_slice(
        self,
        upstream_id: str,
        interval: int,
        *,
        count: int | None = None,
        start: int | None = None,
        end: int | None = None,
    ):
        """Return a windowed slice for ``(upstream_id, interval)``."""

        buffer = self._buffers.get((upstream_id, interval))
        if buffer is None:
            if count is not None:
                return []
            return xr.DataArray(
                np.empty((0, 2), dtype=object),
                dims=("p", "f"),
                coords={"p": [], "f": ["t", "v"]},
            )

        if count is not None:
            if count <= 0:
                return []
            items = buffer.items()
            subset = items[-min(count, len(items)) :]
            return subset

        ordered = buffer.ordered_array()

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
        upstream_id: str,
        interval: int,
        items: Iterable[tuple[int, Any]],
    ) -> None:
        """Merge historical ``items`` with existing cache contents."""

        buffer = self._ensure_buffer(upstream_id, interval)
        result = self._backfill_merger.merge(buffer, interval, items)

        if result.bucketed_items:
            self.backfill_state.mark_ranges(upstream_id, interval, result.ranges)

        if result.merged_items:
            buffer.replace(result.merged_items)
        else:
            buffer.replace([])

        key = (upstream_id, interval)
        prev_last = self._last_ts.get(key)
        if result.merged_items:
            last_ts = result.merged_items[-1][0]
            if prev_last is None:
                self._missing[key] = False
            elif last_ts != prev_last:
                self._missing[key] = prev_last + interval != last_ts
            self._last_ts[key] = last_ts


__all__ = ["NodeCache"]
