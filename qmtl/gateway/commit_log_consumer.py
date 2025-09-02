from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Iterable, Iterator, Tuple

from cachetools import TTLCache

from . import metrics as gw_metrics


class CommitLogDeduplicator:
    """Filter out duplicate commit-log records.

    Records are identified by the triple ``(node_id, bucket_ts, input_window_hash)``.
    Entries are cached for ``ttl`` seconds (or until ``maxsize`` is exceeded).
    Only the first occurrence of each triple within the cache window is yielded;
    subsequent duplicates are discarded silently.
    """

    def __init__(self, *, maxsize: int = 1024, ttl: float = 60.0) -> None:
        self._seen: TTLCache[Tuple[str, int, str], None] = TTLCache(
            maxsize=maxsize, ttl=ttl
        )

    def filter(
        self, records: Iterable[Tuple[str, int, str, Any]]
    ) -> Iterator[Tuple[str, int, str, Any]]:
        for node_id, bucket_ts, input_hash, payload in records:
            key = (node_id, bucket_ts, input_hash)
            if key in self._seen:
                gw_metrics.commit_duplicate_total.inc()
                gw_metrics.commit_duplicate_total._val = (
                    gw_metrics.commit_duplicate_total._value.get()
                )  # type: ignore[attr-defined]
                continue
            self._seen[key] = None
            yield (node_id, bucket_ts, input_hash, payload)


try:  # pragma: no cover - aiokafka optional
    from aiokafka import AIOKafkaConsumer
except Exception:  # pragma: no cover - import guard
    AIOKafkaConsumer = Any  # type: ignore[misc]


class CommitLogConsumer:
    """Consume commit-log records from Kafka.

    The consumer wraps an :class:`AIOKafkaConsumer` and deduplicates records
    with :class:`CommitLogDeduplicator` before handing them off to a downstream
    processor.  Offsets are committed after the processor successfully
    completes.
    """

    def __init__(
        self,
        consumer: AIOKafkaConsumer,  # type: ignore[misc]
        *,
        topic: str,
        group_id: str,
        commit_offsets: bool = True,
        deduplicator: CommitLogDeduplicator | None = None,
    ) -> None:
        self._consumer = consumer
        self.topic = topic
        self.group_id = group_id
        self._commit_offsets = commit_offsets
        self._dedup = deduplicator or CommitLogDeduplicator()

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def _poll_raw(
        self, timeout_ms: int | None = None
    ) -> list[tuple[str, int, str, Any]]:
        result = await self._consumer.getmany(timeout_ms=timeout_ms)
        records: list[tuple[str, int, str, Any]] = []
        for messages in result.values():
            for msg in messages:
                node_id, bucket_ts, input_hash, payload = json.loads(msg.value)
                records.append((node_id, bucket_ts, input_hash, payload))
        return records

    async def consume(
        self,
        processor: Callable[[list[tuple[str, int, str, Any]]], Awaitable[None]],
        *,
        timeout_ms: int | None = None,
    ) -> None:
        """Poll once and pass records to ``processor``.

        Only unique records are forwarded.  Offsets are committed after the
        processor returns when ``commit_offsets`` is ``True``.
        """

        raw_records = await self._poll_raw(timeout_ms)
        records = list(self._dedup.filter(raw_records))
        if records:
            await processor(records)
        if self._commit_offsets:
            await self._consumer.commit()


__all__ = ["CommitLogDeduplicator", "CommitLogConsumer"]
