from __future__ import annotations

import inspect
import json
import os
from collections.abc import Iterable
from typing import Any, TYPE_CHECKING
import logging
from enum import Enum

from opentelemetry import trace

import numpy as np
import xarray as xr
import httpx

from .cache_view import CacheView
from .backfill_state import BackfillState
from .exceptions import NodeValidationError, InvalidParameterError
from . import arrow_cache
from . import metrics as sdk_metrics
from . import node_validation as default_validator
from . import hash_utils as default_hash_utils
from .event_service import EventRecorderService
from .util import parse_interval

if TYPE_CHECKING:  # pragma: no cover - type checking import
    from qmtl.io import HistoryProvider, EventRecorder

from qmtl.common import compute_node_id

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class MatchMode(str, Enum):
    """Tag matching behaviour for :class:`TagQueryNode`.

    ``MatchMode.ANY`` selects queues containing any of the requested tags,
    while ``MatchMode.ALL`` requires every tag to be present.
    """

    ANY = "any"
    ALL = "all"


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
        """Return event-time watermark for the cache.

        Watermark is defined as ``min(last_ts) - allowed_lateness`` across all
        observed ``(upstream_id, interval)`` pairs. Returns ``None`` if the
        cache has not seen any data yet.
        """
        last = [ts for ts in self._last_ts.values() if ts is not None]
        if not last:
            return None
        return int(min(last)) - int(allowed_lateness)

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

    def __init__(
        self,
        input: "Node" | Iterable["Node"] | None = None,
        compute_fn=None,
        name: str | None = None,
        interval: int | str | None = None,
        period: int | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
        schema: dict | None = None,
        *,
        allowed_lateness: int = 0,
        on_late: str = "recompute",
        runtime_compat: str = "loose",
        validator=default_validator,
        hash_utils=default_hash_utils,
        event_service: EventRecorderService | None = None,
    ) -> None:
        self.validator = validator
        self.hash_utils = hash_utils
        self.event_service = event_service

        if isinstance(interval, str):
            interval = parse_interval(interval)

        validator.validate_compute_fn(compute_fn)
        (
            validated_name,
            validated_tags,
            interval_val,
            period_val,
        ) = validator.validate_node_params(
            name,
            tags,
            interval,
            period,
            config,
            schema,
        )

        if isinstance(interval_val, str):
            interval_val = parse_interval(interval_val)

        self.input = input
        self.inputs = validator.normalize_inputs(input)
        self.compute_fn = compute_fn
        self.name = validated_name
        self.interval = interval_val
        self.period = period_val
        self.tags = validated_tags
        self.config = config or {}
        self.schema = schema or {}
        self.execute = True
        self.kafka_topic: str | None = None
        if arrow_cache.ARROW_AVAILABLE and os.getenv("QMTL_ARROW_CACHE") == "1":
            self.cache = arrow_cache.NodeCacheArrow(period_val or 0)
        else:
            self.cache = NodeCache(period_val or 0)
        self.pre_warmup = True
        # Event-time controls
        self.allowed_lateness: int = int(allowed_lateness)
        self.on_late: str = on_late
        self._last_watermark: int | None = None
        # Late event sink for optional side output policy
        self._late_events: list[tuple[str, int, Any]] = []
        # Runtime reuse policy surface
        self.runtime_compat: str = runtime_compat  # "strict" | "loose"

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return (
            f"Node(name={self.name!r}, interval={self.interval}, period={self.period})"
        )

    def add_tag(self, tag: str) -> "Node":
        """Append ``tag`` to :attr:`tags` if missing and return ``self``."""
        validated_tag = self.validator.validate_tag(tag)
        if validated_tag not in self.tags:
            self.tags.append(validated_tag)
        return self

    # --- hashing helpers -------------------------------------------------
    @property
    def node_type(self) -> str:
        return self.__class__.__name__

    @property
    def code_hash(self) -> str:
        return self.hash_utils.code_hash(self.compute_fn)

    @property
    def config_hash(self) -> str:
        return self.hash_utils.config_hash(self.config)

    @property
    def schema_hash(self) -> str:
        return self.hash_utils.schema_hash(self.schema)

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
        # Validate parameters
        if not isinstance(upstream_id, str):
            raise InvalidParameterError("upstream_id must be a string")
        if not upstream_id.strip():
            raise InvalidParameterError("upstream_id must not be empty")
        
        if not isinstance(interval, int):
            raise InvalidParameterError("interval must be an integer")
        if interval <= 0:
            raise InvalidParameterError("interval must be positive")
        
        if not isinstance(timestamp, int):
            raise InvalidParameterError("timestamp must be an integer")
        if timestamp < 0:
            raise InvalidParameterError("timestamp must not be negative")
        
        if on_missing not in ("skip", "fail"):
            raise InvalidParameterError("on_missing must be 'skip' or 'fail'")
        
        with tracer.start_as_current_span(
            "node.feed", attributes={"node.id": self.node_id}
        ):
            self.cache.append(upstream_id, interval, timestamp, payload)
            sdk_metrics.observe_nodecache_resident_bytes(
                self.node_id, self.cache.resident_bytes
            )

        if self.event_service is not None:
            self.event_service.record(self.node_id, interval, timestamp, payload)

        if self.pre_warmup and self.cache.ready():
            self.pre_warmup = False

        missing = self.cache.missing_flags().get(upstream_id, {}).get(interval, False)
        if missing:
            if on_missing == "fail":
                raise RuntimeError("gap detected")
            if on_missing == "skip":
                return False

        # Event-time gating & late-data handling
        try:
            self._last_watermark = self.cache.watermark(allowed_lateness=self.allowed_lateness)  # type: ignore[attr-defined]
        except Exception:
            self._last_watermark = None

        if self.pre_warmup or self.compute_fn is None:
            return False

        if self._last_watermark is None:
            return False

        bucket_ts = timestamp - (timestamp % (interval or 1))
        wm = int(self._last_watermark)

        if bucket_ts < wm:
            policy = (self.on_late or "recompute").lower()
            if policy == "ignore":
                return False
            if policy == "side_output":
                self._late_events.append((upstream_id, bucket_ts, payload))
                return False
            return True

        if bucket_ts >= wm:
            return True

        return False

    def watermark(self) -> int | None:
        """Return the last computed watermark for this node."""
        return self._last_watermark

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
            raise NodeValidationError(
                "processing node requires at least one upstream (node.input에 올바른 업스트림 노드를 지정했는지 확인하세요)"
            )


class StreamInput(SourceNode):
    """Represents an upstream data stream placeholder.

    ``history_provider`` and ``event_service`` must be supplied when the
    instance is created. For backward compatibility an ``event_recorder`` may
    be provided and will be wrapped by :class:`EventRecorderService`. These
    dependencies are immutable for the lifetime of the node.
    """

    def __init__(
        self,
        tags: list[str] | None = None,
        interval: int | str | None = None,
        period: int | None = None,
        *,
        history_provider: "HistoryProvider" | None = None,
        event_recorder: "EventRecorder" | None = None,
        event_service: EventRecorderService | None = None,
        validator=default_validator,
        hash_utils=default_hash_utils,
        **node_kwargs,
    ) -> None:
        if event_service is None and event_recorder is not None:
            event_service = EventRecorderService(event_recorder)
        super().__init__(
            input=None,
            compute_fn=None,
            name="stream_input",
            interval=interval,
            period=period,
            tags=tags or [],
            validator=validator,
            hash_utils=hash_utils,
            event_service=event_service,
            **node_kwargs,
        )
        self._history_provider = history_provider
        if history_provider and hasattr(history_provider, "bind_stream"):
            history_provider.bind_stream(self)
        if event_service and hasattr(event_service, "bind_stream"):
            event_service.bind_stream(self)

    @property
    def history_provider(self) -> "HistoryProvider" | None:
        """Return the configured history provider."""
        return self._history_provider

    @history_provider.setter
    def history_provider(self, value: "HistoryProvider" | None) -> None:
        raise AttributeError("history_provider is read-only and must be provided via __init__")

    @property
    def event_recorder(self) -> "EventRecorder" | None:
        """Return the configured event recorder, if any."""
        if self.event_service is None:
            return None
        return getattr(self.event_service, "recorder", None)

    @event_recorder.setter
    def event_recorder(self, value: "EventRecorder" | None) -> None:
        raise AttributeError("event_recorder is read-only and must be provided via __init__")

    async def load_history(self, start: int, end: int) -> None:
        """Load historical data if a provider was configured."""
        if not self.history_provider or self.interval is None:
            return
        from .backfill_engine import BackfillEngine

        engine = BackfillEngine(self.history_provider)
        engine.submit(self, start, end)
        await engine.wait()


class TagQueryNode(SourceNode):
    """Node that selects upstream queues by tag and interval.

    Parameters
    ----------
    query_tags:
        Tags to subscribe to.
    interval:
        Bar interval in seconds or string shorthand.
    period:
        Number of bars to retain in the cache.
    match_mode:
        Tag matching mode. ``MatchMode.ANY`` subscribes to queues containing
        any of ``query_tags`` while ``MatchMode.ALL`` requires every tag.
    """

    def __init__(
        self,
        query_tags: list[str],
        *,
        interval: int | str,
        period: int,
        match_mode: MatchMode = MatchMode.ANY,
        compute_fn=None,
        name: str | None = None,
    ) -> None:
        # Validate query_tags
        if not isinstance(query_tags, list):
            raise InvalidParameterError("query_tags must be a list")
        if not query_tags:
            raise InvalidParameterError("query_tags must not be empty")
        
        validated_query_tags = []
        seen_tags = set()
        for tag in query_tags:
            validated_tag = default_validator.validate_tag(tag)
            if validated_tag in seen_tags:
                raise InvalidParameterError(f"duplicate query tag: {validated_tag!r}")
            seen_tags.add(validated_tag)
            validated_query_tags.append(validated_tag)
        
        super().__init__(
            input=None,
            compute_fn=compute_fn,
            name=name or "tag_query",
            interval=interval,
            period=period,
            tags=list(validated_query_tags),
        )
        self.query_tags = validated_query_tags
        self.match_mode = match_mode
        self.upstreams: list[str] = []
        self.execute = False

    def update_queues(self, queues: list[str]) -> None:
        """Update ``upstreams`` and execution flag."""
        prev_exec = self.execute
        prev_set = set(self.upstreams)
        new_set = set(queues)
        added = new_set - prev_set
        removed = prev_set - new_set

        self.upstreams = list(queues)
        self.execute = bool(queues)

        warmup_reset = False
        if added:
            self.pre_warmup = True
            warmup_reset = True

        if removed and self.interval is not None:
            for q in removed:
                self.cache.drop(q, self.interval)

        if not self.upstreams:
            logger.warning(
                "tag_query.update.empty",
                extra={"node_id": self.node_id},
            )

        if (
            self.execute != prev_exec
            or added
            or removed
            or self.upstreams != list(prev_set)
        ):
            logger.info(
                "tag_query.update",
                extra={
                    "node_id": self.node_id,
                    "queues": self.upstreams,
                    "execute": self.execute,
                    "warmup_reset": warmup_reset,
                },
            )
