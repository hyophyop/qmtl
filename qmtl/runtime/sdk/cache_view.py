from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar, cast
from dataclasses import dataclass

from . import metrics as sdk_metrics
from .protocols import NodeLike


PayloadT = TypeVar("PayloadT")
CacheEntry = tuple[int, PayloadT]
CacheLeaf = Sequence[CacheEntry[PayloadT]]


@dataclass(slots=True)
class CacheWindow(Generic[PayloadT]):
    """Windowed slice of cache entries for a single ``(node_id, interval)``."""

    node_id: str
    interval: int | str
    _rows: CacheLeaf[PayloadT]

    def latest(self) -> PayloadT | None:
        if not self._rows:
            return None
        _, payload = self._rows[-1]
        return payload

    def as_frame(self, *, ts_col: str = "ts"):
        """Return a pandas DataFrame with a timestamp column."""

        import pandas as pd

        if not self._rows:
            return pd.DataFrame(columns=[ts_col])

        timestamps, payloads = zip(*self._rows)
        if payloads and isinstance(payloads[0], Mapping):
            frame = pd.DataFrame(list(payloads))
        else:
            frame = pd.DataFrame({"value": payloads})
        frame.insert(0, ts_col, list(timestamps))
        return frame

    def require_columns(self, columns: Sequence[str], *, ts_col: str = "ts") -> None:
        """Raise if any ``columns`` are missing from the window payload."""

        frame = self.as_frame(ts_col=ts_col)
        missing = [col for col in columns if col not in frame]
        if missing:
            raise ValueError(
                f"CacheWindow[{self.node_id!r}, {self.interval!r}] missing columns: {missing}"
            )

    def to_series(
        self,
        column: str,
        *,
        ts_col: str = "ts",
        dropna: bool = True,
    ):
        """Return a pandas Series indexed by ``ts_col`` for ``column``."""

        frame = self.as_frame(ts_col=ts_col)
        if column not in frame:
            raise KeyError(
                f"column={column!r} not found in CacheWindow[{self.node_id!r}, {self.interval!r}]"
            )
        series = frame.set_index(ts_col)[column]
        return series.dropna() if dropna else series

    def rows(self) -> list[CacheEntry[PayloadT]]:
        """Return the underlying rows (ts, payload) as a new list."""

        return list(self._rows)


CacheViewData = Mapping[Any, Any] | CacheLeaf[PayloadT]


class CacheView(Generic[PayloadT]):
    """Simple hierarchical read-only view over a cache snapshot.

    When ``track_access`` is ``True`` every accessed ``(upstream_id, interval)``
    pair is recorded and can be retrieved via :meth:`access_log`.
    """

    def __init__(
        self,
        data: CacheViewData[PayloadT],
        *,
        track_access: bool = False,
        artifact_plane: Any | None = None,
        access_log: list[tuple[str, int]] | None = None,
        path: tuple[Any, ...] = (),
    ) -> None:
        self._data = data
        self._track_access = track_access
        self._access_log = access_log if access_log is not None else []
        self._path = path
        self._artifact_plane = artifact_plane

    def __getitem__(self, key: Any) -> Any:
        data = object.__getattribute__(self, "_data")
        if isinstance(data, Mapping):
            return self._get_from_mapping(data, key)
        if isinstance(data, Sequence):
            return data[key]
        raise TypeError("unsupported operation")

    def _get_from_mapping(self, data: Mapping[Any, Any], key: Any) -> Any:
        if _looks_like_node(key):
            key = key.node_id

        new_path = self._path + (key,)
        self._maybe_record_access(new_path)
        value = data[key]
        if isinstance(value, CacheView):
            value = object.__getattribute__(value, "_data")

        if isinstance(value, Sequence):
            return CacheView(
                value,
                track_access=self._track_access,
                artifact_plane=self._artifact_plane,
                access_log=self._access_log,
                path=new_path,
            )
        if isinstance(value, Mapping):
            return CacheView(
                value,
                track_access=self._track_access,
                artifact_plane=self._artifact_plane,
                access_log=self._access_log,
                path=new_path,
            )
        return value

    def _maybe_record_access(self, path: tuple[Any, ...]) -> None:
        if not (self._track_access and len(path) == 2):
            return
        u, i = path
        if isinstance(u, str) and isinstance(i, int):
            self._access_log.append((u, i))
            sdk_metrics.observe_cache_read(u, i)

    def __getattr__(self, name: str) -> Any:
        # Avoid treating private/dunder attributes as mapping access
        if name.startswith("_") or (name.startswith("__") and name.endswith("__")):
            raise AttributeError(name)
        data = object.__getattribute__(self, "_data")
        if isinstance(data, Mapping) and name in data:
            return self.__getitem__(name)
        raise AttributeError(name)

    def latest(self) -> CacheEntry[PayloadT] | None:
        data = object.__getattribute__(self, "_data")
        if isinstance(data, Sequence):
            return data[-1] if data else None
        raise AttributeError("latest")

    def table(self):  # Arrow-friendly convenience for Arrow backend adapters
        from typing import Sequence as _Seq
        data = object.__getattribute__(self, "_data")
        if isinstance(data, _Seq):
            try:  # pragma: no cover - exercised via Arrow tests
                import pyarrow as pa
                import pickle
            except Exception as e:  # pragma: no cover - optional dependency
                raise AttributeError("table") from e
            ts = [int(t) for t, _ in data]
            vals = [pickle.dumps(v) for _, v in data]
            return pa.table({
                "t": pa.array(ts, pa.int64()),
                "v": pa.array(vals, pa.binary()),
            })
        raise AttributeError("table")

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return f"CacheView({self._data!r})"

    # ------------------------------------------------------------------
    def access_log(self) -> list[tuple[str, int]]:
        """Return list of accessed ``(upstream_id, interval)`` pairs."""
        return list(self._access_log)

    # ------------------------------------------------------------------
    def feature_artifacts(
        self,
        factor: Any,
        *,
        instrument: str | None = None,
        dataset_fingerprint: str | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> list[tuple[int, Any]]:
        """Return immutable feature artifacts for ``factor`` when available."""

        if self._artifact_plane is None:
            return []
        result = self._artifact_plane.load_series(
            factor,
            instrument=instrument,
            dataset_fingerprint=dataset_fingerprint,
            start=start,
            end=end,
        )
        return cast(list[tuple[int, Any]], result)

    # ------------------------------------------------------------------
    def as_frame(
        self,
        node: "NodeLike" | str,
        interval: int,
        *,
        window: int | None = None,
        columns: Sequence[str] | None = None,
    ):
        """Delegate to :func:`cache_view_tools.as_frame`."""

        from .cache_view_tools import as_frame as _as_frame

        return _as_frame(self, node, interval, window=window, columns=columns)

    def window(
        self,
        node: "NodeLike" | str,
        interval: int,
        length: int | None = None,
        *,
        count: int | None = None,
    ) -> CacheWindow[PayloadT] | list[CacheEntry[PayloadT]]:
        """Return a cache slice for ``(node, interval)``.

        - Legacy mode: ``length`` (positional) → delegate to ``cache_view_tools.window`` and
          return a ``list[(ts, value)]``.
        - Helper mode: ``count=`` → return a :class:`CacheWindow` with DataFrame/Series helpers.
        """

        if length is not None and count is not None:
            raise ValueError("specify only one of length or count")

        if count is not None or length is None:
            entries = self[node][interval]
            if isinstance(entries, CacheView):
                entries = object.__getattribute__(entries, "_data")
            if not isinstance(entries, Sequence):
                raise TypeError("Cache entry is not sequence-like; cannot build window")

            effective_count = count if count is not None else len(entries)
            subset = [] if effective_count <= 0 else list(entries[-effective_count:])
            node_id = node.node_id if hasattr(node, "node_id") else node
            return CacheWindow(node_id=node_id, interval=interval, _rows=subset)

        from .cache_view_tools import window as _window

        return _window(self, node, interval, length)

    def align_frames(
        self,
        specs: Sequence[tuple["NodeLike" | str, int]],
        *,
        window: int | None = None,
        columns: Mapping["NodeLike" | str, Sequence[str]] | Sequence[str] | None = None,
    ):
        """Delegate to :func:`cache_view_tools.align_frames`."""

        from .cache_view_tools import align_frames as _align_frames

        return _align_frames(self, specs, window=window, columns=columns)


def _looks_like_node(obj: Any) -> bool:
    return hasattr(obj, "node_id") and hasattr(obj, "node_type")
