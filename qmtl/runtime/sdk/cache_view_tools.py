from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd


class NodeLike(Protocol):
    node_id: str


@dataclass(frozen=True)
class CacheFrame:
    """Pandas-backed view over a cache leaf."""

    frame: pd.DataFrame

    def returns(self, *, window: int = 1, dropna: bool = True):
        """Percentage change over ``window`` periods."""

        return self.pct_change(window=window, dropna=dropna)

    def pct_change(self, *, window: int = 1, dropna: bool = True):
        if window < 1:
            raise ValueError("window must be >= 1")

        target = self.frame if self.frame.shape[1] > 1 else self.frame.iloc[:, 0]
        changed = target.pct_change(periods=window)
        return changed.dropna() if dropna else changed

    def validate_columns(self, required: Sequence[str]) -> "CacheFrame":
        missing = [column for column in required if column not in self.frame.columns]
        if missing:
            raise KeyError(f"Missing columns: {', '.join(missing)}")
        return self

    def align_with(self, *others: "CacheFrame") -> list["CacheFrame"]:
        frames = [self.frame, *(other.frame for other in others)]
        if not frames:
            return []

        common_index = frames[0].index
        for frame in frames[1:]:
            common_index = common_index.intersection(frame.index)
        common_index = common_index.sort_values()

        return [CacheFrame(frame.loc[common_index]) for frame in frames]


def window(view, node: "NodeLike" | str, interval: int, length: int) -> list[tuple[Any, Any]]:
    """Return the trailing ``length`` entries for ``(node, interval)``."""

    if length < 0:
        raise ValueError("length must be non-negative")

    series_view = view[node][interval]
    data = _as_sequence(series_view)
    if length == 0:
        return []
    return list(data[-length:])


def as_frame(
    view,
    node: "NodeLike" | str,
    interval: int,
    *,
    window: int | None = None,
    columns: Sequence[str] | None = None,
) -> CacheFrame:
    """Convert a cache leaf into a :class:`CacheFrame`."""

    series = _slice_series(view, node, interval, window)
    timestamps: list[int] = []
    values: list[Any] = []
    for item in series:
        if not isinstance(item, Sequence) or isinstance(item, (str, bytes, bytearray)):
            raise TypeError("cache leaf entries must be (timestamp, value) pairs")
        if len(item) != 2:
            raise ValueError("cache leaf entries must unpack into timestamp and value")
        ts, value = item
        timestamps.append(int(ts))
        values.append(value)

    frame = _build_frame(timestamps, values, columns)
    return CacheFrame(frame)


def align_frames(
    view,
    specs: Sequence[tuple["NodeLike" | str, int]],
    *,
    window: int | None = None,
    columns: Mapping[object, Sequence[str]] | Sequence[str] | None = None,
) -> list[CacheFrame]:
    """Materialize and align multiple cache leaves on their shared timestamps."""

    frames: list[CacheFrame] = []
    for node, interval in specs:
        column_spec: Sequence[str] | None
        if isinstance(columns, Mapping):
            column_spec = columns.get(node)
        else:
            column_spec = columns
        frames.append(as_frame(view, node, interval, window=window, columns=column_spec))

    if not frames:
        return []
    return frames[0].align_with(*frames[1:])


def _slice_series(
    view, node: "NodeLike" | str, interval: int, window: int | None
) -> Sequence[Any]:
    series_view = view[node][interval]
    data = _as_sequence(series_view)
    if window is None:
        return data[:]
    if window < 0:
        raise ValueError("window must be non-negative")
    if window == 0:
        return []
    return data[-window:]


def _as_sequence(series_view: Any) -> Sequence[Any]:
    data = series_view
    series_cls = series_view.__class__
    # CacheView exposes its backing data via _data; avoid importing to keep module decoupled
    if series_cls.__name__ == "CacheView" and series_cls.__module__ == "qmtl.runtime.sdk.cache_view":
        data = object.__getattribute__(series_view, "_data")
    if data is None:
        return []
    if isinstance(data, (str, bytes, bytearray)):
        raise TypeError("cache leaf must be a sequence of (timestamp, value) pairs")
    if isinstance(data, Sequence):
        return data
    if isinstance(data, Iterable):
        return list(data)
    raise TypeError("cache leaf must be a sequence of (timestamp, value) pairs")


def _build_frame(
    timestamps: Sequence[int], values: Sequence[Any], columns: Sequence[str] | None
) -> pd.DataFrame:
    if not values:
        if columns is None:
            return pd.DataFrame(index=pd.Index([], name="t"))
        return pd.DataFrame(columns=list(columns), index=pd.Index([], name="t"))

    first_value = values[0]
    if isinstance(first_value, Mapping):
        inferred_columns = columns or _collect_mapping_columns(values)
        _validate_mapping_columns(values, inferred_columns)
        rows = [{column: value.get(column) for column in inferred_columns} for value in values]
        return pd.DataFrame(rows, index=pd.Index(timestamps, name="t"), columns=list(inferred_columns))

    if isinstance(first_value, Sequence) and not isinstance(first_value, (str, bytes, bytearray)):
        inferred_columns = columns or [f"value_{i}" for i in range(len(first_value))]
        if columns is not None and len(first_value) != len(columns):
            raise ValueError("sequence values must match the number of columns")
        rows = [
            {column: value[i] for i, column in enumerate(inferred_columns)}
            for value in values
        ]
        return pd.DataFrame(rows, index=pd.Index(timestamps, name="t"), columns=list(inferred_columns))

    inferred_columns = columns or ["value"]
    if columns is not None and len(inferred_columns) != 1:
        raise ValueError("scalar values can only map to a single column")
    return pd.DataFrame(values, index=pd.Index(timestamps, name="t"), columns=list(inferred_columns))


def _collect_mapping_columns(values: Sequence[Mapping[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for value in values:
        keys.update(value.keys())
    return sorted(keys)


def _validate_mapping_columns(values: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    missing = []
    for column in columns:
        if not all(column in value for value in values):
            missing.append(column)
    if missing:
        raise KeyError(f"Missing columns: {', '.join(missing)}")
