from __future__ import annotations

from typing import Any, Sequence

import numpy as np


class RingBuffer:
    """Lightweight fixed-length buffer for ``(timestamp, payload)`` pairs.

    The buffer stores items in a two-column ``numpy`` array. Consumers can append
    new entries, request the ordered contents, or replace the buffer with a new
    set of items. Ordering is always returned from oldest to newest entries.
    """

    def __init__(self, period: int) -> None:
        if period <= 0:
            msg = "RingBuffer period must be a positive integer"
            raise ValueError(msg)
        self.period = period
        self._data = np.empty((period, 2), dtype=object)
        self._data[:] = None
        self._offset = 0
        self._filled = 0

    def append(self, timestamp: int, payload: Any) -> None:
        """Append ``payload`` at ``timestamp`` overwriting the oldest entry."""

        self._data[self._offset, 0] = timestamp
        self._data[self._offset, 1] = payload
        self._offset = (self._offset + 1) % self.period
        if self._filled < self.period:
            self._filled += 1

    def ordered_array(self) -> np.ndarray:
        """Return a new array ordered from oldest to newest entries."""

        if self._filled < self.period:
            return np.concatenate((self._data[self._filled :], self._data[: self._filled]))
        return np.concatenate((self._data[self._offset :], self._data[: self._offset]))

    def items(self) -> list[tuple[int, Any]]:
        """Return buffered items ordered from oldest to newest."""

        return [
            (int(ts), payload)
            for ts, payload in self.ordered_array()
            if ts is not None
        ]

    def latest(self) -> tuple[int, Any] | None:
        """Return the most recent ``(timestamp, payload)`` pair or ``None``."""

        if self._filled == 0:
            return None
        idx = (self._offset - 1) % self.period
        ts = self._data[idx, 0]
        if ts is None:
            return None
        return int(ts), self._data[idx, 1]

    def replace(self, items: Sequence[tuple[int, Any]]) -> None:
        """Replace buffer contents with ``items`` ordered oldest -> newest."""

        trimmed = list(items)[-self.period :]
        data = np.empty((self.period, 2), dtype=object)
        data[:] = None
        for idx, (ts, payload) in enumerate(trimmed):
            data[idx, 0] = ts
            data[idx, 1] = payload
        self._data = data
        self._filled = min(len(trimmed), self.period)
        self._offset = len(trimmed) % self.period if self._filled else 0

    @property
    def filled(self) -> int:
        return self._filled

    @property
    def offset(self) -> int:
        return self._offset

    @property
    def data(self) -> np.ndarray:
        return self._data

    @property
    def nbytes(self) -> int:
        return self._data.nbytes


__all__ = ["RingBuffer"]
