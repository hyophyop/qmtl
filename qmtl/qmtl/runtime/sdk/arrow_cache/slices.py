"""Arrow slice primitives used by the cache backend."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .dependencies import ARROW_AVAILABLE, pa


class _Slice:
    """Fixed-width Arrow-backed circular buffer."""

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
    def table(self):
        return pa.table({"t": self.ts, "v": self.vals})

    def slice_table(self, start: int, end: int):
        start = max(0, start)
        end = min(len(self.ts), end)
        length = max(0, end - start)
        return pa.table({"t": self.ts.slice(start, length), "v": self.vals.slice(start, length)})

    @property
    def resident_bytes(self) -> int:
        return int(self.ts.nbytes) + int(self.vals.nbytes)


class _SliceView(Sequence):
    """Sequence view into a :class:`_Slice`."""

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

    def table(self):
        return self._slice.slice_table(self._start, self._end)


__all__ = ["_Slice", "_SliceView"]
