from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class CacheView:
    """Simple hierarchical read-only view over a cache snapshot.

    When ``track_access`` is ``True`` every accessed ``(upstream_id, interval)``
    pair is recorded and can be retrieved via :meth:`access_log`.
    """

    def __init__(
        self,
        data: Any,
        *,
        track_access: bool = False,
        access_log: list[tuple[str, int]] | None = None,
        path: tuple[Any, ...] = (),
    ) -> None:
        self._data = data
        self._track_access = track_access
        self._access_log = access_log if access_log is not None else []
        self._path = path

    def __getitem__(self, key: Any) -> Any:
        if isinstance(self._data, Mapping):
            new_path = self._path + (key,)
            if self._track_access and len(new_path) == 2:
                u, i = new_path
                if isinstance(u, str) and isinstance(i, int):
                    self._access_log.append((u, i))
            return CacheView(
                self._data[key],
                track_access=self._track_access,
                access_log=self._access_log,
                path=new_path,
            )
        if isinstance(self._data, Sequence):
            return self._data[key]
        raise TypeError("unsupported operation")

    def __getattr__(self, name: str) -> Any:
        if isinstance(self._data, Mapping) and name in self._data:
            return self.__getitem__(name)
        raise AttributeError(name)

    def latest(self) -> Any:
        if isinstance(self._data, Sequence):
            return self._data[-1] if self._data else None
        raise AttributeError("latest")

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return f"CacheView({self._data!r})"

    # ------------------------------------------------------------------
    def access_log(self) -> list[tuple[str, int]]:
        """Return list of accessed ``(upstream_id, interval)`` pairs."""
        return list(self._access_log)


