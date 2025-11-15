"""Shared interfaces for persistent repositories."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Optional, Protocol, Sequence


class DatabaseDriver(Protocol):
    """Minimal async database driver interface used by repositories."""

    def convert(self, query: str) -> str:  # pragma: no cover - interface default
        return query

    async def execute(self, query: str, *params: Any) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def fetchone(
        self, query: str, *params: Any
    ) -> Optional[Sequence[Any]]:  # pragma: no cover - interface
        raise NotImplementedError

    async def fetchall(
        self, query: str, *params: Any
    ) -> List[Sequence[Any]]:  # pragma: no cover - interface
        raise NotImplementedError


class RedisClient(Protocol):
    """Subset of redis async client features required by repositories."""

    async def get(self, key: str) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    async def set(self, key: str, value: Any) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    async def delete(self, key: str) -> Any:  # pragma: no cover - interface
        raise NotImplementedError


AuditLogger = Callable[[str, dict[str, Any]], Awaitable[None]]
