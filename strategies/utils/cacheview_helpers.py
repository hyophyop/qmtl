"""Helpers for extracting data from :class:`qmtl.sdk.cache_view.CacheView`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node


def fetch_series(
    view: CacheView | None,
    node: Node,
    side: str | None = None,
    level: int | None = None,
    feature: str | None = None,
) -> list[Any]:
    """Return ordered series for ``node`` from ``view``.

    When ``side``, ``level`` and ``feature`` are provided the function traverses
    the hierarchy ``time → side → level → feature`` collecting the feature
    values across all available timestamps. If they are omitted the raw payloads
    for the node's ``interval`` are returned.
    """

    if view is None:
        return []

    try:
        data = view[node]._data
    except Exception:  # pragma: no cover - defensive
        return []

    # Simple ``interval -> [(ts, payload)]`` layout
    if (
        isinstance(data, Mapping)
        and node.interval in data
        and isinstance(data[node.interval], list)
    ):
        try:
            entries_view = view[node][node.interval]
            entries = getattr(entries_view, "_data", entries_view)
            return [payload for _, payload in entries]
        except Exception:  # pragma: no cover - defensive
            return []

    # ``time -> side -> level -> feature`` layout
    series: list[Any] = []
    history = view[node]
    if not isinstance(history._data, Mapping):
        return series

    for t in sorted(history._data):
        try:
            entry: Any = history[t]
            if side is not None:
                entry = entry[side]
            if level is not None:
                entry = entry[level]
            if feature is not None:
                entry = entry[feature]
            value = getattr(entry, "_data", entry)
            series.append(value)
        except Exception:  # pragma: no cover - defensive
            continue
    return series


def latest_value(view: CacheView | None, node: Node, default: float = 0.0) -> Any:
    """Return the latest payload for ``node`` from ``view`` or ``default``."""

    if view is None:
        return default

    try:
        entries_view = view[node][node.interval]
        entries = getattr(entries_view, "_data", entries_view)
        if not entries:
            return default
        value = entries[-1][1]
        return getattr(value, "_data", value)
    except Exception:  # pragma: no cover - defensive
        return default


def level_series(
    view: CacheView | None, time: int, side: str, feature: str
) -> list[Any]:
    """Return ``feature`` values across levels for ``side`` at ``time``."""

    if view is None:
        return []

    try:
        levels = view[time][side]
        if not isinstance(levels._data, Mapping):
            return []
    except Exception:  # pragma: no cover - defensive
        return []

    values: list[Any] = []
    for lvl in sorted(levels._data):
        try:
            feats = levels[lvl]
            if feature in feats._data:
                val = feats[feature]
                values.append(getattr(val, "_data", val))
        except Exception:  # pragma: no cover - defensive
            continue
    return values


def value_at(
    view: CacheView | None,
    time: int,
    side: str,
    level: int,
    feature: str,
    default: Any | None = None,
) -> Any | None:
    """Return cached value or ``default`` for ``(time, side, level, feature)``."""

    if view is None:
        return default

    try:
        val = view[time][side][level][feature]
        return getattr(val, "_data", val)
    except Exception:  # pragma: no cover - defensive
        return default


__all__ = [
    "fetch_series",
    "latest_value",
    "level_series",
    "value_at",
]

