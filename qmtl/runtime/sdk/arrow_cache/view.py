"""Read-only views over Arrow-backed cache storage."""
from __future__ import annotations

from typing import Any, Dict, Iterable

from .instrumentation import CacheInstrumentation, NOOP_INSTRUMENTATION
from .slices import _Slice, _SliceView


class ArrowCacheView:
    """Hierarchical read-only view backed by Arrow ``_Slice`` objects."""

    def __init__(
        self,
        data: Dict[str, Dict[int, _Slice]],
        *,
        track_access: bool = False,
        artifact_plane: Any | None = None,
        metrics: CacheInstrumentation | None = None,
    ) -> None:
        self._data = data
        self._track_access = track_access
        self._access_log: list[tuple[str, int]] = []
        self._artifact_plane = artifact_plane
        self._metrics = metrics or NOOP_INSTRUMENTATION

    def __getitem__(self, key: Any):
        if hasattr(key, "node_id"):
            key = getattr(key, "node_id")
        mp = self._data[key]
        return _SecondLevelView(
            mp,
            str(key),
            self._track_access,
            self._access_log,
            self._metrics,
        )

    def __getattr__(self, name: str):  # pragma: no cover - convenience
        if name in self._data:
            return self.__getitem__(name)
        raise AttributeError(name)

    def access_log(self) -> list[tuple[str, int]]:
        return list(self._access_log)

    def feature_artifacts(
        self,
        factor: Any,
        *,
        instrument: str | None = None,
        dataset_fingerprint: str | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> list[tuple[int, Any]]:
        if self._artifact_plane is None:
            return []
        return self._artifact_plane.load_series(
            factor,
            instrument=instrument,
            dataset_fingerprint=dataset_fingerprint,
            start=start,
            end=end,
        )


class _SecondLevelView:
    def __init__(
        self,
        data: Dict[int, _Slice],
        upstream: str,
        track_access: bool,
        log: list[tuple[str, int]],
        metrics: CacheInstrumentation,
    ) -> None:
        self._data = data
        self._upstream = upstream
        self._track_access = track_access
        self._log = log
        self._metrics = metrics

    def __getitem__(self, key: int):
        if self._track_access:
            self._log.append((self._upstream, key))
            self._metrics.observe_cache_read(self._upstream, key)
        return _SliceView(self._data[key])

    def keys(self) -> Iterable[int]:  # pragma: no cover - convenience
        return self._data.keys()


__all__ = ["ArrowCacheView", "_SecondLevelView"]
