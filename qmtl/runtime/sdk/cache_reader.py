from __future__ import annotations

import json
from typing import Any, Mapping

import numpy as np
import xarray as xr

from .cache_ring_buffer import RingBuffer


class CacheWindowReader:
    """Read-only helpers for exporting cache contents."""

    def __init__(
        self, buffers: Mapping[tuple[str, int], RingBuffer], *, period: int
    ) -> None:
        self._buffers = buffers
        self._period = period

    def view_data(self) -> dict[str, dict[int, list[tuple[int, Any]]]]:
        data: dict[str, dict[int, list[tuple[int, Any]]]] = {}
        for (upstream, interval), buffer in self._buffers.items():
            data.setdefault(upstream, {})[interval] = buffer.items()
        return data

    def snapshot(self) -> dict[str, dict[int, list[tuple[int, Any]]]]:
        """Return a deep copy of the cache contents for tests."""

        data = self.view_data()
        return {u: {i: list(items) for i, items in mp.items()} for u, mp in data.items()}

    def input_window_hash(self, *, hash_utils) -> str:
        ordered: list[tuple[str, int, list[tuple[int, Any]]]] = []
        for (upstream, interval), buffer in sorted(self._buffers.items()):
            ordered.append((upstream, interval, buffer.items()))
        blob = json.dumps(ordered, sort_keys=True, default=repr).encode()
        return hash_utils._sha256(blob)

    def as_xarray(self) -> xr.DataArray:
        upstreams = sorted({u for u, _ in self._buffers.keys()})
        intervals = sorted({i for _, i in self._buffers.keys()})
        data = np.empty((len(upstreams), len(intervals), self._period, 2), dtype=object)
        data[:] = None
        for u_idx, upstream in enumerate(upstreams):
            for i_idx, interval in enumerate(intervals):
                buffer = self._buffers.get((upstream, interval))
                if buffer is not None:
                    data[u_idx, i_idx] = buffer.ordered_array()
        da = xr.DataArray(
            data,
            dims=("u", "i", "p", "f"),
            coords={
                "u": upstreams,
                "i": intervals,
                "p": list(range(self._period)),
                "f": ["t", "v"],
            },
        )
        da.data = da.data.view()
        da.data.setflags(write=False)
        return da


__all__ = ["CacheWindowReader"]
