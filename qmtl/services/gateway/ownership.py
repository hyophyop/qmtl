from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, Dict, Set, cast

from .database import PostgresDatabase, pg_try_advisory_lock, pg_advisory_unlock
from . import metrics as gw_metrics

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
        # Best-effort owner tracking to record handoffs for metrics.
        # Maps lock key -> last known owner id.
        self._last_owner: Dict[int, str] = {}
        # Keys that previously failed acquisition attempts. When ownership is
        # later obtained for any of these keys, a reassignment metric is
        # recorded. This enables the metric to be triggered without requiring
        # explicit owner identifiers.
        self._pending: Set[int] = set()

    async def acquire(self, key: int, owner: Optional[str] = None) -> bool:
        """Attempt to acquire ownership for ``key``."""

        if await self._try_kafka_acquire(key, owner):
            return True

        acquired = await self._try_db_acquire(key, owner)
        if acquired:
            return True
        self._pending.add(key)
        return False

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

    async def _try_kafka_acquire(self, key: int, owner: Optional[str]) -> bool:
        if self._kafka is None:
            return False
        try:
            if not await self._kafka.acquire(key):
                self._pending.add(key)
                return False
            self._record_reassignment(key, owner)
            self._remember_owner(key, owner)
            return True
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Kafka ownership acquisition failed")
            return False

    async def _try_db_acquire(self, key: int, owner: Optional[str]) -> bool:
        assert self._db._pool is not None, "database not connected"
        async with self._db._pool.acquire() as conn:
            acquired = await pg_try_advisory_lock(conn, key)
            if not acquired:
                return False
            self._record_reassignment(key, owner)
            self._remember_owner(key, owner)
            return True

    def _record_reassignment(self, key: int, owner: Optional[str]) -> None:
        if key in self._pending:
            gw_metrics.owner_reassign_total.inc()
            self._pending.discard(key)
            return
        if owner is None:
            return
        last = self._last_owner.get(key)
        if last is None or last == owner:
            return
        gw_metrics.owner_reassign_total.inc()
        metric = cast(Any, gw_metrics.owner_reassign_total)
        metric._val = metric._value.get()

    def _remember_owner(self, key: int, owner: Optional[str]) -> None:
        if owner is not None:
            self._last_owner[key] = owner


__all__ = ["OwnershipManager", "KafkaOwnership"]
