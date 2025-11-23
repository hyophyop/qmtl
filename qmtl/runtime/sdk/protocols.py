from __future__ import annotations

"""Protocols for SDK runtime dependencies used by the runner."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class HistoryProviderProtocol(Protocol):
    """Minimal interface for history providers consumed by :mod:`runner`."""

    def bind_stream(self, node: object) -> None: ...


class HistoryProviderNodeProtocol(Protocol):
    """Nodes that can coerce history providers provided by the runner."""

    def _coerce_history_provider(
        self, provider: HistoryProviderProtocol | object | None
    ) -> HistoryProviderProtocol | object | None: ...


@runtime_checkable
class TagQueryManagerProtocol(Protocol):
    """Subset of :class:`TagQueryManager` used by the runner."""

    async def resolve_tags(self, *, offline: bool = False) -> None: ...

    async def stop(self) -> None: ...


class StrategyWithTagManagerProtocol(Protocol):
    """Strategies annotated with an optional tag query manager."""

    tag_query_manager: TagQueryManagerProtocol | None


class MetricWithValueProtocol(Protocol):
    """Metrics that expose both ``set`` and a cached ``_val`` attribute."""

    _val: float

    def set(self, value: float) -> None: ...
