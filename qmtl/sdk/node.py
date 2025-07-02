from __future__ import annotations

import hashlib
import inspect
import json
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING
import logging

import numpy as np
import xarray as xr
import httpx
import asyncio

from .cache_view import CacheView
from .backfill_state import BackfillState
from .util import parse_interval, parse_period
from . import arrow_cache

if TYPE_CHECKING:  # pragma: no cover - type checking import
    from qmtl.io import HistoryProvider, EventRecorder

from qmtl.dagmanager import compute_node_id

logger = logging.getLogger(__name__)


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

    def append(self, u: str, interval: int, timestamp: int, payload: Any) -> None:
        """Insert ``payload`` with ``timestamp`` for ``(u, interval)``."""
        buf = self._ensure_buffer(u, interval)
        timestamp_bucket = timestamp - (timestamp % interval)
        prev = self._last_ts.get((u, interval))
        if prev is not None and prev + interval != timestamp_bucket:
            self._missing[(u, interval)] = True
        else:
            self._missing[(u, interval)] = False
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

    def view(self, *, track_access: bool = False) -> CacheView:
        """Return a :class:`CacheView` over the current cache contents.

        The returned view is read-only and mirrors the structure of
        ``_snapshot()`` without creating intermediate copies. When
        ``track_access`` is ``True`` every accessed ``(upstream_id, interval)``
        pair is recorded and can be retrieved via
        :meth:`CacheView.access_log`.
        """
        data: dict[str, dict[int, list[tuple[int, Any]]]] = {}
        for (u, i), buf in self._buffers.items():
            data.setdefault(u, {})[i] = [
                (int(t), v) for t, v in self._ordered_array(u, i) if t is not None
            ]
        return CacheView(data, track_access=track_access)

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

    def as_xarray(self) -> xr.DataArray:
        """Return a read-only ``xarray`` view of the internal tensor.

        Callers must **not** mutate the returned :class:`xarray.DataArray`.
        """
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
        """Return a windowed slice for ``(u, interval)``.

        If ``count`` is given a ``list`` of the latest ``count`` items is
        returned. Otherwise an ``xarray.DataArray`` slice from ``start`` to
        ``end`` along the period dimension is provided. Unknown upstreams or
        intervals yield an empty result.
        """

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


class Node:
    """Represents a processing node in a strategy DAG.

    ``compute_fn`` must accept exactly **one argument** – a :class:`CacheView`
    returned by :py:meth:`NodeCache.view`. The view provides read-only access to
    the cached data and mirrors the structure returned by
    :py:meth:`NodeCache.view`. Positional arguments other than the cache view are
    **not** supported. ``input`` may be a single ``Node`` or an iterable of
    ``Node`` instances. Passing dictionaries is no longer supported. Tags can be
    assigned at initialization or later via :py:meth:`add_tag`.
    """

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_inputs(inp: Node | Iterable[Node] | None) -> list[Node]:
        if inp is None:
            return []
        if isinstance(inp, Node):
            return [inp]
        if isinstance(inp, Mapping):
            raise TypeError("mapping inputs no longer supported")
        if isinstance(inp, Iterable):
            return list(inp)
        raise TypeError("invalid input type")

    def __init__(
        self,
        input: Node | Iterable[Node] | None = None,
        compute_fn=None,
        name: str | None = None,
        interval: int | str | None = None,
        period: int | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
        schema: dict | None = None,
    ) -> None:
        interval_val = parse_interval(interval) if interval is not None else None
        period_val = parse_period(period) if period is not None else None

        if compute_fn is not None:
            sig = inspect.signature(compute_fn)
            positional = [
                p
                for p in sig.parameters.values()
                if p.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            has_var_positional = any(
                p.kind == inspect.Parameter.VAR_POSITIONAL
                for p in sig.parameters.values()
            )
            if len(positional) != 1 or has_var_positional:
                raise TypeError(
                    "compute_fn must accept exactly one positional argument (지원되지 않는 함수 시그니처). compute_fn(view) 형태로 작성했는지 확인하세요"
                )

        self.input = input
        self.inputs = self._normalize_inputs(input)
        self.compute_fn = compute_fn
        self.name = name
        self.interval = interval_val
        self.period = period_val
        self.tags = tags or []
        self.config = config or {}
        self.schema = schema or {}
        self.execute = True
        self.queue_topic: str | None = None
        if arrow_cache.ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1":
            self.cache = arrow_cache.NodeCacheArrow(period_val or 0)
        else:
            self.cache = NodeCache(period_val or 0)
        self.pre_warmup = True

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return (
            f"Node(name={self.name!r}, interval={self.interval}, period={self.period})"
        )

    def add_tag(self, tag: str) -> "Node":
        """Append ``tag`` to :attr:`tags` if missing and return ``self``."""
        if tag not in self.tags:
            self.tags.append(tag)
        return self

    # --- hashing helpers -------------------------------------------------
    @staticmethod
    def _sha256(data: bytes) -> str:
        try:
            h = hashlib.sha256()
            h.update(data)
            return h.hexdigest()
        except Exception:
            # Fallback if sha256 unavailable
            h = hashlib.sha3_256()
            h.update(data)
            return h.hexdigest()

    @staticmethod
    def _sha3(data: bytes) -> str:
        h = hashlib.sha3_256()
        h.update(data)
        return h.hexdigest()

    @property
    def node_type(self) -> str:
        return self.__class__.__name__

    @property
    def code_hash(self) -> str:
        if self.compute_fn is None:
            return self._sha256(b"null")
        try:
            source = inspect.getsource(self.compute_fn).encode()
        except (OSError, TypeError):
            source = getattr(self.compute_fn, "__code__", None)
            if source is not None:
                source = source.co_code
            else:
                source = repr(self.compute_fn).encode()
        return self._sha256(source)

    @property
    def config_hash(self) -> str:
        data = json.dumps(self.config, sort_keys=True).encode()
        return self._sha256(data)

    @property
    def schema_hash(self) -> str:
        data = json.dumps(self.schema, sort_keys=True).encode()
        return self._sha256(data)

    @property
    def node_id(self) -> str:
        return compute_node_id(
            self.node_type,
            self.code_hash,
            self.config_hash,
            self.schema_hash,
        )

    # --- runtime cache handling -----------------------------------------
    def feed(
        self,
        upstream_id: str,
        interval: int,
        timestamp: int,
        payload,
        *,
        on_missing: str = "skip",
    ) -> bool:
        """Insert new data into ``cache`` and signal compute readiness.

        Returns ``True`` when the node has collected enough data to execute its
        ``compute_fn``. The function **never** triggers execution directly.
        """
        self.cache.append(upstream_id, interval, timestamp, payload)

        recorder = getattr(self, "event_recorder", None)
        if recorder is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(recorder.persist(self.node_id, interval, timestamp, payload))
            else:
                loop.create_task(
                    recorder.persist(self.node_id, interval, timestamp, payload)
                )

        if self.pre_warmup and self.cache.ready():
            self.pre_warmup = False

        missing = self.cache.missing_flags().get(upstream_id, {}).get(interval, False)
        if missing:
            if on_missing == "fail":
                raise RuntimeError("gap detected")
            if on_missing == "skip":
                return False

        return not self.pre_warmup and self.compute_fn is not None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "interval": self.interval,
            "period": self.period,
            "tags": list(self.tags),
            "inputs": [n.node_id for n in self.inputs],
            "code_hash": self.code_hash,
            "schema_hash": self.schema_hash,
            "pre_warmup": self.pre_warmup,
        }


class SourceNode(Node):
    """Base class for nodes without upstream dependencies."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("input", None)
        super().__init__(*args, **kwargs)


class ProcessingNode(Node):
    """Node that processes data from one or more upstream nodes."""

    def __init__(self, input: Node | Iterable[Node], *args, **kwargs) -> None:
        super().__init__(input=input, *args, **kwargs)
        if not self.inputs:
            raise ValueError(
                "processing node requires at least one upstream (node.input에 올바른 업스트림 노드를 지정했는지 확인하세요)"
            )


class StreamInput(SourceNode):
    """Represents an upstream data stream placeholder."""

    def __init__(
        self,
        tags: list[str] | None = None,
        interval: int | str | None = None,
        period: int | None = None,
        *,
        history_provider: "HistoryProvider" | None = None,
        event_recorder: "EventRecorder" | None = None,
    ) -> None:
        super().__init__(
            input=None,
            compute_fn=None,
            name="stream_input",
            interval=interval,
            period=period,
            tags=tags or [],
        )
        self.history_provider = history_provider
        self.event_recorder = event_recorder

    async def load_history(self, start: int, end: int) -> None:
        """Load historical data if a provider was configured."""
        if not self.history_provider or self.interval is None:
            return
        from .backfill_engine import BackfillEngine

        engine = BackfillEngine(self.history_provider)
        engine.submit(self, start, end)
        await engine.wait()


class TagQueryNode(SourceNode):
    """Node that selects upstream queues by tag and interval."""

    def __init__(
        self,
        query_tags: list[str],
        *,
        interval: int | str,
        period: int,
        match_mode: str = "any",
        compute_fn=None,
        name: str | None = None,
    ) -> None:
        super().__init__(
            input=None,
            compute_fn=compute_fn,
            name=name or "tag_query",
            interval=interval,
            period=period,
            tags=list(query_tags),
        )
        self.query_tags = list(query_tags)
        self.match_mode = match_mode
        self.upstreams: list[str] = []
        self.execute = False

    def update_queues(self, queues: list[str]) -> None:
        """Update ``upstreams`` and execution flag."""
        prev_exec = self.execute
        prev_q = self.upstreams
        self.upstreams = list(queues)
        self.execute = bool(queues)
        if self.execute != prev_exec or self.upstreams != prev_q:
            logger.info(
                "tag_query.update",
                extra={
                    "node_id": self.node_id,
                    "queues": self.upstreams,
                    "execute": self.execute,
                },
            )

