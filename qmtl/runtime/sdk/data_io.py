from __future__ import annotations

"""Interfaces for I/O operations.

This module defines the abstract I/O interfaces used by the SDK.
Concrete implementations live under ``qmtl.runtime.io``.
"""

from typing import Any, Protocol, runtime_checkable
from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd

from .protocols import StreamLike


class DataFetcher(Protocol):
    """Retrieve historical rows for a node."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        ...


@runtime_checkable
class HistoryBackend(Protocol):
    """Low-level storage backend used by :class:`HistoryProvider`."""

    async def read_range(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Return rows for ``[start, end)``."""
        ...

    async def write_rows(
        self, rows: pd.DataFrame, *, node_id: str, interval: int
    ) -> None:
        """Persist ``rows`` for ``(node_id, interval)``."""
        ...

    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return inclusive timestamp ranges already stored."""
        ...


@dataclass(slots=True)
class AutoBackfillRequest:
    """Represents a pending backfill window for a ``(node_id, interval)`` pair."""

    node_id: str
    interval: int
    start: int
    end: int


class HistoryProvider(ABC):
    """Load historical data into node caches."""

    def bind_stream(self, stream: StreamLike) -> None:
        """Associate this provider with ``stream``.

        The default implementation stores ``stream.node_id`` in
        ``self._stream_id`` so subclasses can infer a table name or similar
        identifier. Storage backends may override this to perform additional
        setup.
        """
        self._stream_id = stream.node_id

    @abstractmethod
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Return data in ``[start, end)`` for ``node_id`` and ``interval``."""
        ...

    @abstractmethod
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return timestamp ranges available for ``node_id`` and ``interval``."""
        ...

    @abstractmethod
    async def ensure_range(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Ensure history for ``[start, end]`` exists."""

    @abstractmethod
    async def fill_missing(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Populate gaps in ``[start, end]`` for ``node_id`` and ``interval``."""
        ...


class EventRecorder(ABC):
    """Persist processed node data."""

    def bind_stream(self, stream: StreamLike) -> None:
        """Associate this recorder with ``stream``.

        The default implementation records ``stream.node_id`` in
        ``self._stream_id`` for backends that use the identifier as a table
        name. Subclasses may override as needed.
        """
        self._stream_id = stream.node_id

    @abstractmethod
    async def persist(
        self, node_id: str, interval: int, timestamp: int, payload: Any
    ) -> None:
        """Store ``payload`` for ``(node_id, interval, timestamp)``."""
        ...


__all__ = [
    "DataFetcher",
    "HistoryBackend",
    "AutoBackfillRequest",
    "HistoryProvider",
    "EventRecorder",
]
