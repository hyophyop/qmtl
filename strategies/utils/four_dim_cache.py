"""Simple four-dimensional cache utility.

Keys
----
Entries are addressed by ``(time, side, level, metric)`` tuples. ``time`` and
``side`` may be any hashable representing temporal and directional axes while
``level`` and ``metric`` identify price level and metric name respectively.

The cache supports basic ``get``, ``set`` and ``invalidate`` operations and is
used across multiple indicator nodes to share a common caching scheme.
"""

from __future__ import annotations

from typing import Any, Hashable


class FourDimCache:
    """Dictionary-backed cache with four-dimensional keys."""

    def __init__(self) -> None:
        self._data: dict[tuple[Hashable, Hashable, Hashable, Hashable], Any] = {}

    def get(
        self,
        time: Hashable,
        side: Hashable,
        level: Hashable,
        metric: Hashable,
        default: Any | None = None,
    ) -> Any | None:
        """Retrieve a value for ``(time, side, level, metric)`` or ``default``."""

        return self._data.get((time, side, level, metric), default)

    def set(
        self,
        time: Hashable,
        side: Hashable,
        level: Hashable,
        metric: Hashable,
        value: Any,
    ) -> None:
        """Store ``value`` under ``(time, side, level, metric)``."""

        self._data[(time, side, level, metric)] = value

    def invalidate(
        self,
        time: Hashable | None = None,
        side: Hashable | None = None,
        level: Hashable | None = None,
        metric: Hashable | None = None,
    ) -> None:
        """Invalidate matching cache entries.

        Parameters are treated as wildcards when ``None`` and entries matching
        all non-``None`` dimensions are removed.
        """

        keys = list(self._data.keys())
        for t, s, l, m in keys:
            if time is not None and t != time:
                continue
            if side is not None and s != side:
                continue
            if level is not None and l != level:
                continue
            if metric is not None and m != metric:
                continue
            del self._data[(t, s, l, m)]
