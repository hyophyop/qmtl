from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from qmtl.dagmanager.kafka_admin import partition_key

try:
    from aiokafka import AIOKafkaProducer
except Exception:  # pragma: no cover - aiokafka optional
    AIOKafkaProducer = Any  # type: ignore

logger = logging.getLogger(__name__)


class CommitLogWriter:
    """Write commit-log records to a compacted Kafka topic.

    The writer uses a Kafka producer configured for idempotent transactional
    publishing.  Each call to :meth:`publish_bucket` writes all records for a
    bucket within a single transaction which is either committed or aborted.
    """

    def __init__(self, producer: AIOKafkaProducer, topic: str) -> None:  # type: ignore[misc]
        self._producer = producer
        self._topic = topic

    async def publish_bucket(
        self,
        bucket_ts: int,
        interval: int | None,
        records: Iterable[tuple[str, str, Any]],
    ) -> None:
        """Publish ``records`` for ``interval``/``bucket_ts`` in a transaction.

        Each record is a tuple ``(node_id, input_window_hash, payload)``.  The
        value sent to Kafka contains ``(node_id, bucket_ts, input_window_hash,
        payload)`` serialised as JSON.  The message key combines the
        :func:`~qmtl.dagmanager.kafka_admin.partition_key` for the ``node_id``,
        ``interval`` and ``bucket_ts`` with the ``input_window_hash`` to ensure
        the topic can be compacted.
        """

        await self._producer.begin_transaction()
        try:
            for node_id, input_window_hash, payload in records:
                value = json.dumps(
                    (node_id, bucket_ts, input_window_hash, payload)
                ).encode()
                pkey = partition_key(node_id, interval, bucket_ts)
                key = f"{pkey}:{input_window_hash}".encode()
                await self._producer.send_and_wait(
                    self._topic,
                    key=key,
                    value=value,
                )
            await self._producer.commit_transaction()
        except Exception:  # pragma: no cover - defensive log
            try:
                await self._producer.abort_transaction()
            except Exception:  # pragma: no cover - double failure
                logger.exception("Commit-log abort failed")
            raise


async def create_commit_log_writer(
    bootstrap_servers: str, topic: str, transactional_id: str
) -> CommitLogWriter:
    """Create a :class:`CommitLogWriter` with idempotent producer settings."""

    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        acks="all",
        enable_idempotence=True,
        transactional_id=transactional_id,
    )
    await producer.start()
    return CommitLogWriter(producer, topic)


__all__ = ["CommitLogWriter", "create_commit_log_writer"]
