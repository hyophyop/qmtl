from __future__ import annotations

import logging
from typing import Optional, Protocol

from .database import PostgresDatabase, pg_try_advisory_lock, pg_advisory_unlock

logger = logging.getLogger(__name__)


class KafkaOwnership(Protocol):
    async def acquire(self, key: int) -> bool:
        """Try to obtain Kafka-based ownership for ``key``."""

    async def release(self, key: int) -> None:
        """Release Kafka-based ownership for ``key``."""


class OwnershipManager:
    """Coordinate ownership using Kafka with DB advisory lock fallback."""

    def __init__(self, db: PostgresDatabase, kafka_owner: Optional[KafkaOwnership] = None) -> None:
        self._db = db
        self._kafka = kafka_owner

    async def acquire(self, key: int) -> bool:
        """Attempt to acquire ownership for ``key``."""

        if self._kafka is not None:
            try:
                if await self._kafka.acquire(key):
                    return True
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Kafka ownership acquisition failed")

        assert self._db._pool is not None, "database not connected"
        async with self._db._pool.acquire() as conn:
            return await pg_try_advisory_lock(conn, key)

    async def release(self, key: int) -> None:
        """Release ownership for ``key``."""

        if self._kafka is not None:
            try:
                await self._kafka.release(key)
                return
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Kafka ownership release failed")

        assert self._db._pool is not None, "database not connected"
        async with self._db._pool.acquire() as conn:
            await pg_advisory_unlock(conn, key)


__all__ = ["OwnershipManager", "KafkaOwnership"]
