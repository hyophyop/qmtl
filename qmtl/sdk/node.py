from __future__ import annotations

import hashlib
import inspect
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import xarray as xr
import httpx

from .cache_view import CacheView
from .backfill_state import BackfillState

from qmtl.dagmanager import compute_node_id


class NodeCache:
    """4-D tensor cache ``C[u,i,p,t]`` implemented with ``xarray``.

    Besides the tensor itself the cache tracks the last timestamp for every
    ``(u, interval)`` pair and whether the most recently appended timestamp
    introduced a gap (``last_timestamp + interval != timestamp``).
    """

    def __init__(self, period: int) -> None:
        self.period = period
        self._tensor = xr.DataArray(
            np.empty((0, 0, period, 2), dtype=object),
            dims=("u", "i", "p", "f"),
            coords={"u": [], "i": [], "p": list(range(period)), "f": ["t", "v"]},
        )
        self._last_ts: dict[tuple[str, int], int | None] = {}
        self._missing: dict[tuple[str, int], bool] = {}
        # Pre-computed index mappings and fill counters for readiness checks
        self._u_idx: dict[str, int] = {}
        self._i_idx: dict[int, int] = {}
        self._filled: dict[tuple[str, int], int] = {}
        self.backfill_state = BackfillState()

    # ------------------------------------------------------------------
    def _ensure_coords(self, u: str, interval: int) -> None:
        if u not in self._u_idx:
            self._tensor = self._tensor.reindex(
                u=list(self._tensor.coords["u"].values) + [u], fill_value=None
            )
            # reindex returns read-only memory -> copy to enable mutation
            self._tensor = xr.DataArray(
                self._tensor.data.copy(), dims=self._tensor.dims, coords=self._tensor.coords
            )
            self._u_idx[u] = len(self._tensor.coords["u"]) - 1
        if (u, interval) not in self._last_ts:
            self._last_ts[(u, interval)] = None  # type: ignore[assignment]
            self._missing[(u, interval)] = False
            self._filled[(u, interval)] = 0
        if interval not in self._i_idx:
            self._tensor = self._tensor.reindex(
                i=list(self._tensor.coords["i"].values) + [interval], fill_value=None
            )
            self._tensor = xr.DataArray(
                self._tensor.data.copy(), dims=self._tensor.dims, coords=self._tensor.coords
            )
            self._i_idx[interval] = len(self._tensor.coords["i"]) - 1

    def append(self, u: str, interval: int, timestamp: int, payload: Any) -> None:
        """Insert ``payload`` with ``timestamp`` for ``(u, interval)``."""
        self._ensure_coords(u, interval)
        timestamp_bucket = timestamp - (timestamp % interval)
        prev = self._last_ts.get((u, interval))
        if prev is not None and prev + interval != timestamp_bucket:
            self._missing[(u, interval)] = True
        else:
            self._missing[(u, interval)] = False
        self._last_ts[(u, interval)] = timestamp_bucket
        u_idx = self._u_idx[u]
        i_idx = self._i_idx[interval]
        arr = self._tensor.data[u_idx, i_idx]
        arr[:-1] = arr[1:]
        arr[-1, 0] = timestamp_bucket
        arr[-1, 1] = payload
        self._tensor.data[u_idx, i_idx] = arr
        filled = self._filled.get((u, interval), 0)
        if filled < self.period:
            filled += 1
        self._filled[(u, interval)] = filled

    # ------------------------------------------------------------------
    def ready(self) -> bool:
        if not self._u_idx or not self._i_idx:
            return False
        for key, count in self._filled.items():
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
        for u in self._tensor.coords["u"].values:
            u_idx = self._u_idx[u]
            result[u] = {}
            for i in self._tensor.coords["i"].values:
                i_idx = self._i_idx[i]
                slice_ = self._tensor.data[u_idx, i_idx]
                result[u][i] = [(int(t), v) for t, v in slice_ if t is not None]
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
        for u in self._tensor.coords["u"].values:
            u_idx = self._u_idx[u]
            data[u] = {}
            for i in self._tensor.coords["i"].values:
                i_idx = self._i_idx[i]
                slice_ = self._tensor.data[u_idx, i_idx]
                data[u][i] = [(int(t), v) for t, v in slice_ if t is not None]
        return CacheView(data, track_access=track_access)

    def missing_flags(self) -> dict[str, dict[int, bool]]:
        """Return gap flags for all ``(u, interval)`` pairs."""
        result: dict[str, dict[int, bool]] = {}
        for u in self._tensor.coords["u"].values:
            result[u] = {}
            for i in self._tensor.coords["i"].values:
                result[u][i] = self._missing.get((u, i), False)
        return result

    def last_timestamps(self) -> dict[str, dict[int, int | None]]:
        """Return last timestamps for all ``(u, interval)`` pairs."""
        result: dict[str, dict[int, int | None]] = {}
        for u in self._tensor.coords["u"].values:
            result[u] = {}
            for i in self._tensor.coords["i"].values:
                result[u][i] = self._last_ts.get((u, i))
        return result

    def as_xarray(self) -> xr.DataArray:
        """Return a read-only ``xarray`` view of the internal tensor.

        Callers must **not** mutate the returned :class:`xarray.DataArray`.
        """
        da = self._tensor.copy(deep=False)
        da.data = da.data.view()
        da.data.setflags(write=False)
        return da

    # ------------------------------------------------------------------
    def latest(self, u: str, interval: int) -> tuple[int, Any] | None:
        """Return the most recent ``(timestamp, payload)`` for a pair."""
        u_idx = self._u_idx.get(u)
        i_idx = self._i_idx.get(interval)
        if u_idx is None or i_idx is None:
            return None
        if self._filled.get((u, interval), 0) == 0:
            return None
        arr = self._tensor.data[u_idx, i_idx]
        ts = arr[-1, 0]
        if ts is None:
            return None
        return int(ts), arr[-1, 1]

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

        u_idx = self._u_idx.get(u)
        i_idx = self._i_idx.get(interval)
        if u_idx is None or i_idx is None:
            if count is not None:
                return []
            return xr.DataArray(
                np.empty((0, 2), dtype=object),
                dims=("p", "f"),
                coords={"p": [], "f": ["t", "v"]},
            )

        arr = self._tensor.sel(u=u, i=interval)

        if count is not None:
            if count <= 0:
                return []
            subset = arr.isel(p=slice(-count, None)).data
            return [(int(t), v) for t, v in subset if t is not None]

        slice_start = start if start is not None else 0
        slice_end = end if end is not None else self.period

        slice_start = max(0, slice_start + self.period if slice_start < 0 else slice_start)
        slice_end = max(0, slice_end + self.period if slice_end < 0 else slice_end)
        slice_start = min(self.period, slice_start)
        slice_end = min(self.period, slice_end)

        return arr.isel(p=slice(slice_start, slice_end))

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

        self._ensure_coords(u, interval)
        u_idx = self._u_idx[u]
        i_idx = self._i_idx[interval]

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
        arr = self._tensor.data[u_idx, i_idx]
        existing: dict[int, Any] = {
            int(t): v for t, v in arr if t is not None
        }

        ts_payload: dict[int, Any] = dict(existing)
        for ts, payload in backfill_items:
            ts_payload.setdefault(ts, payload)

        merged = sorted(ts_payload.items())[-self.period :]

        new_arr = np.empty((self.period, 2), dtype=object)
        new_arr[:] = None
        start = self.period - len(merged)
        for idx, (ts, payload) in enumerate(merged):
            new_arr[start + idx, 0] = ts
            new_arr[start + idx, 1] = payload

        self._tensor.data[u_idx, i_idx] = new_arr
        self._filled[(u, interval)] = len(merged)

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
    **not** supported.
    """

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_inputs(inp: Node | Iterable[Node] | Mapping[str, Node] | None) -> list[Node]:
        if inp is None:
            return []
        if isinstance(inp, Node):
            return [inp]
        if isinstance(inp, Mapping):
            return list(inp.values())
        if isinstance(inp, Iterable):
            return list(inp)
        raise TypeError("invalid input type")

    def __init__(
        self,
        input: Node | Iterable[Node] | Mapping[str, Node] | None = None,
        compute_fn=None,
        name: str | None = None,
        interval: int | None = None,
        period: int | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
        schema: dict | None = None,
    ) -> None:
        self.input = input
        self.inputs = self._normalize_inputs(input)
        self.compute_fn = compute_fn
        self.name = name
        self.interval = interval
        self.period = period
        self.tags = tags or []
        self.config = config or {}
        self.schema = schema or {}
        self.execute = True
        self.queue_topic: str | None = None
        self.cache = NodeCache(period or 0)
        self.pre_warmup = True

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return (
            f"Node(name={self.name!r}, interval={self.interval}, period={self.period})"
        )

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
    ) -> None:
        """Insert new data into ``cache`` and trigger ``compute_fn`` when ready."""
        self.cache.append(upstream_id, interval, timestamp, payload)
        if self.pre_warmup and self.cache.ready():
            self.pre_warmup = False
        missing = self.cache.missing_flags().get(upstream_id, {}).get(interval, False)
        if missing:
            if on_missing == "fail":
                raise RuntimeError("gap detected")
            if on_missing == "skip":
                return
        if not self.pre_warmup and self.compute_fn:
            self.compute_fn(self.cache.view())

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


class StreamInput(Node):
    """Represents an upstream data stream placeholder."""

    def __init__(self, tags: list[str] | None = None, interval: int | None = None, period: int | None = None) -> None:
        super().__init__(input=None, compute_fn=None, name="stream_input", interval=interval, period=period, tags=tags or [])


class TagQueryNode(Node):
    """Node that selects upstream queues by tag and interval."""

    def __init__(
        self,
        query_tags: list[str],
        *,
        interval: int,
        period: int,
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
        self.upstreams: list[str] = []

    def resolve(self, gateway_url: str | None = None, *, offline: bool = False) -> list[str]:
        """Fetch matching queues from ``gateway_url``.

        If ``gateway_url`` is ``None`` or the request fails, an empty list is
        returned and ``upstreams`` is cleared so the node can operate in
        offline mode.
        """
        if offline or not gateway_url:
            self.upstreams = []
            return []

        url = gateway_url.rstrip("/") + "/queues/by_tag"
        params = {"tags": ",".join(self.query_tags), "interval": self.interval}
        try:
            resp = httpx.get(url, params=params)
            resp.raise_for_status()
        except httpx.RequestError:
            self.upstreams = []
            return []

        queues = resp.json().get("queues", [])
        self.upstreams = queues
        return queues

    async def subscribe_updates(self, gateway_url: str | None = None, *, offline: bool = False) -> None:
        """Subscribe to queue updates via streaming endpoint.

        If ``gateway_url`` is ``None`` or the connection fails, the method
        simply returns and the node remains in offline mode.
        """
        if offline or not gateway_url:
            return

        url = gateway_url.rstrip("/") + "/queues/watch"
        params = {"tags": ",".join(self.query_tags), "interval": self.interval}
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url, params=params) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        queues = data.get("queues")
                        if queues is not None:
                            self.upstreams = queues
        except httpx.RequestError:
            # Connection issues -> operate offline
            return

