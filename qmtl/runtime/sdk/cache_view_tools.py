from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Generic, Mapping, Protocol, Sequence, TypeVar

import polars as pl

PayloadT = TypeVar("PayloadT")
CacheEntry = tuple[int, PayloadT]


class CacheViewLike(Protocol):
    def __getitem__(self, key: Any) -> Any:
        ...

from .protocols import NodeLike


@dataclass(frozen=True)
class CacheFrame(Generic[PayloadT]):
    """Polars-backed view over a cache leaf."""

    frame: pl.DataFrame

    def returns(self, *, window: int = 1, dropna: bool = True):
        """Percentage change over ``window`` periods."""

        return self.pct_change(window=window, dropna=dropna)

    def pct_change(self, *, window: int = 1, dropna: bool = True):
        if window < 1:
            raise ValueError("window must be >= 1")

        value_columns = [col for col in self.frame.columns if col != "t"]
        if not value_columns:
            return pl.Series(name="value", values=[])

        if len(value_columns) == 1:
            series = self.frame.get_column(value_columns[0]).pct_change(window)
            return series.drop_nulls() if dropna else series

        changed = self.frame.select(
            [pl.col("t")]
            + [pl.col(col).pct_change(window).alias(col) for col in value_columns]
        )
        if dropna:
            mask = pl.all_horizontal(
                [pl.col(col).is_not_null() for col in value_columns]
            )
            return changed.filter(mask)
        return changed

    def validate_columns(self, required: Sequence[str]) -> "CacheFrame[PayloadT]":
        missing = [column for column in required if column not in self.frame.columns]
        if missing:
            raise KeyError(f"Missing columns: {', '.join(missing)}")
        return self

    def align_with(self, *others: "CacheFrame[PayloadT]") -> list["CacheFrame[PayloadT]"]:
        frames = [self.frame, *(other.frame for other in others)]
        if not frames:
            return []

        common_ts = set(frames[0].get_column("t").to_list())
        for frame in frames[1:]:
            common_ts &= set(frame.get_column("t").to_list())
        ordered_ts = sorted(common_ts)
        if not ordered_ts:
            return [CacheFrame(_empty_frame([col for col in frame.columns if col != "t"])) for frame in frames]

        return [
            CacheFrame(
                frame.filter(pl.col("t").is_in(ordered_ts)).sort("t")
            )
            for frame in frames
        ]


def window(
    view: CacheViewLike, node: "NodeLike" | str, interval: int, length: int
) -> list[CacheEntry[PayloadT]]:
    """Return the trailing ``length`` entries for ``(node, interval)``."""

    if length < 0:
        raise ValueError("length must be non-negative")

    series_view = view[node][interval]
    data: Sequence[CacheEntry[PayloadT]] = _as_sequence(series_view)
    if length == 0:
        return []
    return list(data[-length:])


def as_frame(
    view: CacheViewLike,
    node: "NodeLike" | str,
    interval: int,
    *,
    window: int | None = None,
    columns: Sequence[str] | None = None,
) -> CacheFrame[PayloadT]:
    """Convert a cache leaf into a :class:`CacheFrame`."""

    series: Sequence[CacheEntry[PayloadT]] = _slice_series(view, node, interval, window)
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
    view: CacheViewLike,
    specs: Sequence[tuple["NodeLike" | str, int]],
    *,
    window: int | None = None,
    columns: Mapping["NodeLike" | str, Sequence[str]] | Sequence[str] | None = None,
) -> list[CacheFrame[PayloadT]]:
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
    view: CacheViewLike, node: "NodeLike" | str, interval: int, window: int | None
) -> Sequence[CacheEntry[PayloadT]]:
    series_view = view[node][interval]
    data: Sequence[CacheEntry[PayloadT]] = _as_sequence(series_view)
    if window is None:
        return data[:]
    if window < 0:
        raise ValueError("window must be non-negative")
    if window == 0:
        return []
    return data[-window:]


def _as_sequence(series_view: Any) -> Sequence[CacheEntry[PayloadT]]:
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
) -> pl.DataFrame:
    if not values:
        return _empty_frame(columns)

    first_value = values[0]
    if isinstance(first_value, Mapping):
        return _frame_from_mapping(timestamps, values, columns)

    if isinstance(first_value, Sequence) and not isinstance(first_value, (str, bytes, bytearray)):
        return _frame_from_sequence(timestamps, values, columns)

    return _frame_from_scalar(timestamps, values, columns)


def _empty_frame(columns: Sequence[str] | None) -> pl.DataFrame:
    if columns is None:
        return pl.DataFrame(schema=[("t", pl.Int64)])
    schema = [("t", pl.Int64), *[(col, pl.Null) for col in columns]]
    return pl.DataFrame(schema=schema)


def _frame_from_mapping(
    timestamps: Sequence[int],
    values: Sequence[Mapping[str, Any]],
    columns: Sequence[str] | None,
) -> pl.DataFrame:
    inferred_columns = columns or _collect_mapping_columns(values)
    _validate_mapping_columns(values, inferred_columns)
    rows = [
        {"t": ts, **{column: value.get(column) for column in inferred_columns}}
        for ts, value in zip(timestamps, values)
    ]
    return pl.DataFrame(rows)


def _frame_from_sequence(
    timestamps: Sequence[int],
    values: Sequence[Sequence[Any]],
    columns: Sequence[str] | None,
) -> pl.DataFrame:
    inferred_columns = columns or [f"value_{i}" for i in range(len(values[0]))]
    if columns is not None and len(values[0]) != len(columns):
        raise ValueError("sequence values must match the number of columns")
    rows = [
        {"t": ts, **{column: value[i] for i, column in enumerate(inferred_columns)}}
        for ts, value in zip(timestamps, values)
    ]
    return pl.DataFrame(rows)


def _frame_from_scalar(
    timestamps: Sequence[int], values: Sequence[Any], columns: Sequence[str] | None
) -> pl.DataFrame:
    inferred_columns = columns or ["value"]
    if columns is not None and len(inferred_columns) != 1:
        raise ValueError("scalar values can only map to a single column")
    rows = [{"t": ts, inferred_columns[0]: value} for ts, value in zip(timestamps, values)]
    return pl.DataFrame(rows)


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
