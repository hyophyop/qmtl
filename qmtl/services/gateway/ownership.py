from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
from typing import Any, Optional, Protocol, Dict, Set, cast, Iterable, Callable

from .database import PostgresDatabase, pg_try_advisory_lock, pg_advisory_unlock
from . import metrics as gw_metrics

logger = logging.getLogger(__name__)


class KafkaOwnership(Protocol):
    async def acquire(self, key: int) -> bool:
        """Try to obtain Kafka-based ownership for ``key``."""

    async def release(self, key: int) -> None:
        """Release Kafka-based ownership for ``key``."""


class KafkaPartitionOwnership:
    """Kafka-based ownership using consumer group partition assignments.

    A key maps deterministically to a Kafka partition. Ownership is granted
    when the local consumer is assigned that partition. Postgres advisory locks
    remain available to :class:`OwnershipManager` as a fallback.
    """

    def __init__(
        self,
        consumer: Any,
        topic: str,
        *,
        partitioner: Callable[[int, int], int] | None = None,
        start_timeout: float = 5.0,
        rebalance_backoff: float = 0.05,
        rebalance_attempts: int = 3,
    ) -> None:
        self._consumer = consumer
        self._topic = topic
        self._partitioner = partitioner or (lambda key, count: key % count)
        self._start_timeout = start_timeout
        self._rebalance_backoff = rebalance_backoff
        self._rebalance_attempts = rebalance_attempts
        self._started = False
        self._start_lock = asyncio.Lock()

    async def acquire(self, key: int) -> bool:
        await self._ensure_started()
        partitions = self._partitions()
        if not partitions:
            return False

        target_partition = self._select_partition(key, partitions)
        assignment = await self._assignment()
        return (self._topic, target_partition) in assignment

    async def release(self, key: int) -> None:  # pragma: no cover - no-op guard
        return None

    async def _ensure_started(self) -> None:
        async with self._start_lock:
            if self._started:
                return
            await asyncio.wait_for(self._consumer.start(), timeout=self._start_timeout)
            self._started = True

    def _partitions(self) -> list[int]:
        parts = self._consumer.partitions_for_topic(self._topic) or set()
        return sorted(parts)

    async def _assignment(self) -> set[tuple[str, int]]:
        for _ in range(self._rebalance_attempts):
            assignment = self._normalize_assignment(self._consumer.assignment())
            if assignment:
                return assignment
            await asyncio.sleep(self._rebalance_backoff)
        return set()

    def _select_partition(self, key: int, partitions: Iterable[int]) -> int:
        as_list = list(partitions)
        if not as_list:
            return 0
        index = self._partitioner(key, len(as_list)) % len(as_list)
        return as_list[index]

    def _normalize_assignment(self, assignment: Iterable[Any]) -> set[tuple[str, int]]:
        normalized: set[tuple[str, int]] = set()
        for item in assignment:
            topic = getattr(item, "topic", None)
            partition = getattr(item, "partition", None)
            if topic is None or partition is None:
                try:
                    topic, partition = item
                except Exception:
                    continue
            normalized.add((str(topic), int(partition)))
        return normalized


def create_kafka_ownership(
    bootstrap_servers: str,
    topic: str,
    group_id: str,
    *,
    start_timeout: float = 5.0,
    rebalance_backoff: float = 0.05,
    rebalance_attempts: int = 3,
) -> KafkaOwnership:
    """Build :class:`KafkaPartitionOwnership` using ``aiokafka`` when available."""

    spec = importlib.util.find_spec("aiokafka")
    if spec is None:
        raise RuntimeError("aiokafka is required for Kafka ownership mode")
    aiokafka = importlib.import_module("aiokafka")
    consumer = aiokafka.AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
    )
    return KafkaPartitionOwnership(
        consumer,
        topic,
        start_timeout=start_timeout,
        rebalance_backoff=rebalance_backoff,
        rebalance_attempts=rebalance_attempts,
    )


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
        # Keys whose ownership currently relies on Postgres advisory locks.
        # Used to ensure DB locks are released even when Kafka ownership is
        # configured but unavailable.
        self._db_owned: Set[int] = set()

    async def acquire(self, key: int, owner: Optional[str] = None) -> bool:
        """Attempt to acquire ownership for ``key``."""

        if await self._try_kafka_acquire(key, owner):
            return True

        acquired = await self._try_db_acquire(key, owner)
        if acquired:
            self._db_owned.add(key)
            return True
        self._pending.add(key)
        return False

    async def release(self, key: int) -> None:
        """Release ownership for ``key``."""

        db_owned = key in self._db_owned
        if self._kafka is not None:
            try:
                await self._kafka.release(key)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Kafka ownership release failed")

        if not db_owned:
            return

        self._db_owned.discard(key)
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


__all__ = [
    "OwnershipManager",
    "KafkaOwnership",
    "KafkaPartitionOwnership",
    "create_kafka_ownership",
]
