from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class CacheView:
    """Simple hierarchical read-only view over a cache snapshot."""

    def __init__(self, data: Any) -> None:
        self._data = data

    def __getitem__(self, key: Any) -> Any:
        if isinstance(self._data, Mapping):
            return CacheView(self._data[key])
        if isinstance(self._data, Sequence):
            return self._data[key]
        raise TypeError("unsupported operation")

    def __getattr__(self, name: str) -> Any:
        if isinstance(self._data, Mapping) and name in self._data:
            return CacheView(self._data[name])
        raise AttributeError(name)

    def latest(self) -> Any:
        if isinstance(self._data, Sequence):
            return self._data[-1] if self._data else None
        raise AttributeError("latest")

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return f"CacheView({self._data!r})"


