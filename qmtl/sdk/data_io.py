from __future__ import annotations

"""Interfaces for I/O operations and legacy re-exports."""

from typing import Protocol, Any
import pandas as pd


class DataFetcher(Protocol):
    """Retrieve historical rows for a node."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        ...


class HistoryProvider(Protocol):
    """Load historical data into node caches."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Return data in ``[start, end)`` for ``node_id`` and ``interval``."""
        ...

    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return timestamp ranges available for ``node_id`` and ``interval``."""
        ...

    async def fill_missing(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Populate gaps in ``[start, end]`` for ``node_id`` and ``interval``."""
        ...


class EventRecorder(Protocol):
    """Persist processed node data."""

    async def persist(
        self, node_id: str, interval: int, timestamp: int, payload: Any
    ) -> None:
        """Store ``payload`` for ``(node_id, interval, timestamp)``."""
        ...


# re-export concrete implementations for backward compatibility
from qmtl.io.historyprovider import QuestDBLoader
from qmtl.io.eventrecorder import QuestDBRecorder

__all__ = [
    "DataFetcher",
    "HistoryProvider",
    "EventRecorder",
    "QuestDBLoader",
    "QuestDBRecorder",
]

