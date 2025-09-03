from __future__ import annotations

"""Interfaces for I/O operations.

This module defines the abstract I/O interfaces used by the SDK.
Concrete implementations live under ``qmtl.io``.
"""

from typing import Protocol, Any, TYPE_CHECKING
from abc import ABC, abstractmethod
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover - for type hints
    from .node import StreamInput


class DataFetcher(Protocol):
    """Retrieve historical rows for a node."""

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        ...


class HistoryProvider(ABC):
    """Load historical data into node caches."""

    def bind_stream(self, stream: "StreamInput") -> None:
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
    async def fill_missing(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Populate gaps in ``[start, end]`` for ``node_id`` and ``interval``."""
        ...


class EventRecorder(ABC):
    """Persist processed node data."""

    def bind_stream(self, stream: "StreamInput") -> None:
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


# re-export concrete implementations for backward compatibility
__all__ = [
    "DataFetcher",
    "HistoryProvider",
    "EventRecorder",
]
